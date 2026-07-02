"""
Text-to-SQL using Google Gemini (gemini-3.1-flash-lite) via google-genai SDK.

Flow:
  1. Build system prompt with full schema context
  2. Ask Gemini to generate Snowflake SQL for the user question
  3. Execute the SQL against Snowflake
  4. Pass results back to Gemini to format as a plain-English answer
  5. On SQL error, retry once so Gemini can self-correct
"""

import os
import re
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv

from .snowflake_client import run_query
from .schema_context import get_system_prompt
from .conversation import ConversationHistory

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
  REPORT.fct_graduation_rate_term, REPORT.fct_enrollment_by_semester_level,
  REPORT.fct_enrollment_term, REPORT.dim_program_episode)
- Only SELECT statements — no INSERT, UPDATE, DELETE, DROP, CREATE
- Never AVG(graduation_rate_pct) or AVG(first_year_retention_rate_pct)
  always SUM numerator / SUM denominator * 100
- school='EN' for College of Engineering (not 'Engineering')
- u_g='G' for Master's, u_g='U' for Undergrad, u_g='D' for Doctoral
- pell='Y' for Pell-eligible
- term_code is VARCHAR — use quotes: '202490' not 202490
- Limit results to 50 rows unless asked for all
- Include ORDER BY for trend/time-series questions
"""

_ANSWER_SYSTEM = """
You are an NJIT Analytics Assistant. The user asked a data question.
SQL was executed and the results are provided below.
Write a clear, concise 2-4 sentence plain-English answer based on the data.
Include the key numbers. Add a brief note if the result has important caveats
(e.g. recent cohorts excluded, small sample size, etc.).
Do NOT repeat the SQL. Just answer naturally.
"""


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
    Returns dict with: answer, sql, dataframe, error
    """
    system_prompt = get_system_prompt() + "\n\n" + _SQL_SYSTEM_ADDENDUM
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=4096,
        temperature=0.1,
    )

    # Step 1: generate SQL
    contents = _build_contents(history, question)
    sql_response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config,
    )
    sql_text = sql_response.text
    sql = _extract_sql(sql_text)

    if not sql:
        return {"answer": sql_text, "sql": None, "dataframe": None, "error": None}

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
        df, error = run_query(sql)

        if error:
            return {
                "answer": f"I couldn't generate valid SQL for this question. Error: {error}",
                "sql": sql, "dataframe": None, "error": error,
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

    return {"answer": answer, "sql": sql, "dataframe": df, "error": None}
