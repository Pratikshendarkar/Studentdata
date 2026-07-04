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
]

# Keywords that suggest a document/RAG question
_RAG_KEYWORDS = [
    "what does the brief say", "according to the report", "in the document",
    "what is the assignment", "explain the methodology", "round 1",
    "the pdf", "the report", "assumption", "formula defined",
]


def classify(question: str) -> str:
    """
    Returns: 'sql', 'rag', 'both', or 'clarify'
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

    return "sql"  # default to SQL path for data context
