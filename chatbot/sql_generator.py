"""
Text-to-SQL using Google Gemini (gemini-3.1-flash-lite) via google-genai SDK.

Flow:
  0. Resolve relative-time phrases ("last year", "this semester") into
     explicit term_code/cohort_year values (see term_resolver.py)
  1. Build system prompt with full schema context
  2. Ask Gemini to generate Snowflake SQL for the user question
  3. Execute the SQL against Snowflake
  4. Pass results back to Gemini to format as a plain-English answer
  5. On SQL error, retry once so Gemini can self-correct
"""

import os
import re
import pandas as pd
import sqlglot
from sqlglot import exp
from google import genai
from google.genai import types
from dotenv import load_dotenv

from .snowflake_client import run_query
from .schema_context import get_system_prompt
from .conversation import ConversationHistory
from .term_resolver import resolve_relative_terms

_STUDENT_ID_GUARD_MESSAGE = (
    "This query cannot be run — student identifiers cannot be returned "
    "in raw form per data privacy policy."
)
_AGGREGATE_TYPES = (exp.Count, exp.Avg, exp.Sum, exp.Min, exp.Max)
# Constructs that mean a column reference is filter/join plumbing -- it
# narrows which rows participate but is never itself returned as an output
# value, e.g. `WHERE student_id IN (...)` or `JOIN ... ON d.student_id =
# e.student_id`. A student_id reference confined to one of these is not a
# governance violation, even though it's "bare" (not aggregate-wrapped).
_FILTER_CONTEXT_TYPES = (exp.Where, exp.Join, exp.In, exp.Exists)

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-3.1-flash-lite"

_SQL_SYSTEM_ADDENDUM = """
## YOUR TASK
When the user asks a data question:
1. Generate a single valid Snowflake SQL SELECT query that answers it.
2. Wrap the SQL in a ```sql ... ``` code block.
3. After the SQL block, write nothing else — the system will execute it
   and send you the results to format into a plain-English answer.

Rules for SQL generation:
- Query ONLY tables in the REPORT schema (REPORT.fct_graduation_rate,
  REPORT.fct_retention_rate_cohort, REPORT.fct_retention_rate_term,
  REPORT.fct_graduation_rate_term, REPORT.fct_enrollment_term,
  REPORT.dim_program_episode, REPORT.PREDICTION_MODEL)
- For enrollment headcounts, use COUNT(DISTINCT student_id) on
  REPORT.fct_enrollment_term, not COUNT(*) or COUNT(student_id) --
  it has one row per program episode per term, so a student with
  multiple programs in the same term has multiple rows
- For dropout/at-risk/prediction questions, use REPORT.PREDICTION_MODEL.
  risk_flag is 'YES'/'NO'/NULL (NULL = graduated, not scored).
  dropout_probability is NULL for graduated students -- filter with
  WHERE risk_flag IS NOT NULL when computing rates over scored students only.
- Only SELECT statements — no INSERT, UPDATE, DELETE, DROP, CREATE
- Never AVG(graduation_rate_pct) or AVG(first_year_retention_rate_pct)
  always SUM numerator / SUM denominator * 100
- school='EN' for College of Engineering (not 'Engineering')
- u_g='G' for Master's, u_g='U' for Undergrad, u_g='D' for Doctoral
- pell='Y' for Pell-eligible
- term_code is VARCHAR in the fct_*/dim_* tables (quote it: '202490') but
  NUMBER in REPORT.PREDICTION_MODEL (do NOT quote it there: term_code = 202610)
- Limit results to 50 rows unless asked for all
- Include ORDER BY for trend/time-series questions
- For "highest/lowest/best/worst <rate>" questions using ORDER BY ... LIMIT 1:
  a rate computed as SUM(numerator)/NULLIF(SUM(denominator),0) is NULL when
  the denominator is 0 (e.g. an immature/not-yet-eligible cohort), and NULL
  sorts FIRST even with ORDER BY ... DESC in Snowflake -- so an ineligible
  row with a NULL rate can wrongly win the LIMIT 1 instead of the real
  highest value. Always add a WHERE clause excluding zero/NULL denominators
  (e.g. WHERE one_year_eligible_cohort_size > 0) before ORDER BY ... LIMIT
  on any computed rate column.
- DATA GOVERNANCE: student_id must NEVER appear as a bare column in a SELECT
  list, ORDER BY, or anywhere its raw value would be returned to the user --
  it may ONLY appear inside an aggregate function (COUNT, AVG, SUM, MIN, MAX),
  e.g. COUNT(DISTINCT student_id). A query that selects student_id directly
  (e.g. to "list student IDs") will be blocked before execution -- write
  aggregate queries instead (counts, rates, distributions) rather than
  returning individual student identifiers.
"""

_ANSWER_SYSTEM = """
You are an NJIT Analytics Assistant. The user asked a data question.
SQL was executed and the results are provided below.
Write a clear, concise 2-4 sentence plain-English answer based on the data.
Include the key numbers. Add a brief note if the result has important caveats
(e.g. recent cohorts excluded, small sample size, etc.).
Do NOT repeat the SQL. Just answer naturally.

CRITICAL: State numbers EXACTLY as they appear in the query results --
never round them or hedge with "approximately", "about", "around", "roughly",
or "~". If a rate is 84.37%, say "84.37%", not "approximately 84%". The
user needs the precise value, not an estimate.
"""


def _violates_student_id_guard(sql: str) -> bool:
    """
    Data-governance guard: student_id must never be returned as an output
    value -- only used inside an aggregate function (COUNT/AVG/SUM/MIN/MAX)
    or as filter/join plumbing (WHERE ... IN (...), JOIN ... ON, EXISTS(...))
    that narrows rows without itself appearing in the result set. Returns
    True if the SQL would return a raw student_id value anywhere (including
    nested subqueries whose own SELECT is the thing ultimately consumed by
    the caller as output), False otherwise.

    If the SQL fails to parse, this returns False (not a violation) so a
    parser limitation on malformed SQL doesn't block unrelated legitimate
    queries -- run_query() will surface the real SQL error regardless.
    """
    try:
        tree = sqlglot.parse_one(sql, read="snowflake")
    except Exception:
        return False

    for column in tree.find_all(exp.Column):
        if column.name.lower() != "student_id":
            continue

        node = column.parent
        wrapped = False
        filtered = False
        while node is not None:
            if isinstance(node, _AGGREGATE_TYPES):
                wrapped = True
                break
            if isinstance(node, _FILTER_CONTEXT_TYPES):
                filtered = True
                break
            node = node.parent

        if not wrapped and not filtered:
            return True

    return False


def _extract_sql(text: str) -> str | None:
    """Extract SQL from a ```sql ... ``` code block."""
    match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"((?:WITH|SELECT)\s+.+)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _build_contents(history: ConversationHistory, question: str) -> list:
    """Build Gemini contents list from history + new question."""
    contents = []
    for msg in history.messages:
        role = "user" if msg.role == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=msg.content)]
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=question)]
    ))
    return contents


def answer_sql_question(question: str, history: ConversationHistory) -> dict:
    """
    Returns dict with: answer, sql, dataframe, error, resolved_question
    """
    try:
        resolved_question = resolve_relative_terms(question)
    except Exception:
        # If term resolution fails (e.g. Snowflake unavailable), fall back to
        # the raw question rather than blocking the whole request.
        resolved_question = question

    system_prompt = get_system_prompt() + "\n\n" + _SQL_SYSTEM_ADDENDUM
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=4096,
        temperature=0.1,
    )

    # Step 1: generate SQL
    contents = _build_contents(history, resolved_question)
    sql_response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config,
    )
    sql_text = sql_response.text
    sql = _extract_sql(sql_text)

    if not sql:
        return {
            "answer": sql_text, "sql": None, "dataframe": None, "error": None,
            "resolved_question": resolved_question,
        }

    # Data-governance guard: never execute a query that returns bare student_id
    if _violates_student_id_guard(sql):
        return {
            "answer": _STUDENT_ID_GUARD_MESSAGE,
            "sql": sql, "dataframe": None, "error": "governance_violation",
            "resolved_question": resolved_question,
        }

    # Step 2: execute SQL
    df, error = run_query(sql)

    # Step 3: retry once on error
    if error:
        retry_msg = (
            f"The SQL produced this error:\n{error}\n\n"
            f"Original SQL:\n```sql\n{sql}\n```\n\n"
            "Please fix it and return only the corrected SQL in a ```sql``` block."
        )
        retry_contents = contents + [
            types.Content(role="model", parts=[types.Part.from_text(text=sql_text)]),
            types.Content(role="user", parts=[types.Part.from_text(text=retry_msg)]),
        ]
        retry_resp = _client.models.generate_content(
            model=MODEL, contents=retry_contents, config=config
        )
        sql = _extract_sql(retry_resp.text) or sql

        if _violates_student_id_guard(sql):
            return {
                "answer": _STUDENT_ID_GUARD_MESSAGE,
                "sql": sql, "dataframe": None, "error": "governance_violation",
                "resolved_question": resolved_question,
            }

        df, error = run_query(sql)

        if error:
            return {
                "answer": f"I couldn't generate valid SQL for this question. Error: {error}",
                "sql": sql, "dataframe": None, "error": error,
                "resolved_question": resolved_question,
            }

    # Step 4: format as plain English
    if df.empty:
        answer = (
            "The query returned no results. This may be because the filters "
            "applied are too specific or no data exists for the requested combination."
        )
    else:
        result_text = df.to_string(index=False, max_rows=20)
        answer_config = types.GenerateContentConfig(
            system_instruction=_ANSWER_SYSTEM,
            max_output_tokens=1024,
            temperature=0.2,
        )
        fmt_resp = _client.models.generate_content(
            model=MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text=f"Question: {question}\n\nQuery results:\n{result_text}"
                )]
            )],
            config=answer_config,
        )
        answer = fmt_resp.text

    return {
        "answer": answer, "sql": sql, "dataframe": df, "error": None,
        "resolved_question": resolved_question,
    }
