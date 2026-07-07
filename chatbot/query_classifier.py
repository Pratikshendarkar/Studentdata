"""
Classifies user questions into:
  - 'sql'  : answerable from Snowflake REPORT tables
  - 'rag'  : answerable from uploaded documents
  - 'both' : needs both data + document context
  - 'clarify' : too ambiguous, needs clarification first

Uses keyword heuristics first (fast, no API call), falls back to
Claude for ambiguous cases.
"""

import re

# Keywords that strongly suggest a data/SQL question
_SQL_KEYWORDS = [
    "graduation rate", "retention rate", "attrition", "enrollment",
    "how many students", "number of students", "pell", "cohort",
    "school", "college", "engineering", "computing", "management",
    "undergrad", "graduate", "master", "doctoral", "phd",
    "semester", "term", "fall", "spring", "2015", "2016", "2017",
    "2018", "2019", "2020", "2021", "2022", "2023", "2024",
    "gpa", "credits", "full-time", "part-time", "firstgen",
    "first generation", "first-gen", "female", "male", "gender", "degree",
    "completed", "dropped", "trend", "average", "percentage", "rate",
    "count", "total", "compare", "which school", "highest", "lowest",
    "arr", "adjusted retention", "dropout", "at risk", "risk score",
    "prediction", "stop out", "stopout", "readmit",
    "continuing students", "prior students",
    "pell gap", "equity gap",
    "term over term", "term-over-term",
    "cohort year", "matured cohort",
    "two year", "2-year", "one year", "1-year",
    "plot", "chart", "graph", "visualize", "visualise",
]

# Keywords that suggest a document/RAG question
_RAG_KEYWORDS = [
    "what does the brief say", "according to the report", "in the document",
    "what is the assignment", "explain the methodology", "round 1",
    "the pdf", "the report", "assumption", "formula defined",
    "the file", "the document", "this scenario", "the scenario",
    "uploaded", "summarize", "summarise", "the upload",
    "mentioned in", "described in", "in the pdf", "in the file",
]


def classify(question: str, has_documents: bool = False) -> str:
    """
    Returns: 'sql', 'rag', 'both', or 'clarify'

    `has_documents` should reflect whether the user has any RAG documents
    currently loaded (e.g. doc_count() > 0). When no SQL/RAG keyword matches
    and a document is loaded, an ambiguous question is routed to 'rag'
    rather than defaulting to 'sql' -- a loaded document is a strong signal
    the user means to ask about it, and the old default silently sent such
    questions into SQL generation, where the LLM would try to answer in
    prose (from the document) that then got mis-parsed as SQL.
    """
    q_lower = question.lower()

    has_sql = any(kw in q_lower for kw in _SQL_KEYWORDS)
    has_rag = any(kw in q_lower for kw in _RAG_KEYWORDS)

    if has_sql and has_rag:
        return "both"
    if has_rag:
        return "rag"
    if has_sql:
        return "sql"

    # Very short or generic questions — try SQL by default since
    # most questions in this context are data questions
    if len(question.split()) <= 3:
        return "clarify"

    if has_documents:
        return "rag"

    return "sql"  # default to SQL path for data context
