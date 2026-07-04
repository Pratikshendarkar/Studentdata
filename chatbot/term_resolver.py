"""
Deterministic term_code / relative-date resolution.

The chatbot has no anchor for "what is the current term" anywhere in its
system prompt or code -- phrases like "last year", "this semester", or
"recent" have no deterministic resolution today, so the LLM has to guess.
This module resolves those phrases against the actual latest term_code
present in the data (not the system clock, since the data pipeline can lag
behind wall-clock time) and appends an explicit, unambiguous annotation to
the user's question before it reaches SQL generation.

term_code format: YYYYTT (TT: 10=Spring, 50=Summer, 90=Fall, 95=Winter).
Mirrors the season logic in rd2_dbt/macros/decode_term_code.sql, which is
dbt-Jinja and not callable at runtime here.
"""

import re
from functools import lru_cache

from .snowflake_client import run_query

_SEASON_BY_SUFFIX = {"10": "Spring", "50": "Summer", "90": "Fall", "95": "Winter"}


def term_year(term_code: str) -> int:
    return int(term_code[:4])


def term_season(term_code: str) -> str:
    suffix = term_code[4:]
    return _SEASON_BY_SUFFIX.get(suffix, "Unknown")


def shift_year(term_code: str, years: int) -> str:
    """Same season, `years` years earlier (negative) or later (positive)."""
    return f"{term_year(term_code) + years}{term_code[4:]}"


def previous_major_term(term_code: str) -> str:
    """Fall -> same-year Spring; Spring -> previous-year Fall."""
    suffix = term_code[4:]
    if suffix == "90":
        return f"{term_year(term_code)}10"
    if suffix == "10":
        return f"{term_year(term_code) - 1}90"
    raise ValueError(f"previous_major_term is only defined for Fall/Spring terms, got {term_code!r}")


@lru_cache(maxsize=1)
def get_current_term() -> str:
    """Latest term_code present in the data (not the system clock)."""
    df, error = run_query("SELECT MAX(term_code) AS max_term FROM REPORT.fct_enrollment_term")
    if error or df.empty:
        raise RuntimeError(f"Could not determine current term: {error}")
    return str(df.iloc[0]["MAX_TERM"])


def reload_current_term() -> None:
    """Bust the cached current-term value (mirrors schema_context.reload_context)."""
    get_current_term.cache_clear()


_RELATIVE_PATTERNS = [
    (re.compile(r"\b(last|past)\s+year\b", re.IGNORECASE), "last_year"),
    (re.compile(r"\b(this|current)\s+year\b", re.IGNORECASE), "this_year"),
    (re.compile(r"\b(last|previous)\s+(semester|term)\b", re.IGNORECASE), "last_term"),
    (re.compile(r"\b(this|current)\s+(semester|term)\b", re.IGNORECASE), "this_term"),
    (re.compile(r"\bpast\s+(\d+)\s+years?\b", re.IGNORECASE), "past_n_years"),
    (re.compile(r"\brecent(ly)?\b", re.IGNORECASE), "recent"),
]


def resolve_relative_terms(question: str) -> str:
    """
    Detect relative-time phrases in `question` and append explicit
    term_code/cohort_year annotations. Appends rather than replacing, so the
    LLM sees both the user's original phrasing and the concrete anchor.
    Questions with no relative-time phrase are returned unchanged.
    """
    current = get_current_term()
    year = term_year(current)
    season = term_season(current)

    annotations = []
    seen_kinds = set()

    for pattern, kind in _RELATIVE_PATTERNS:
        match = pattern.search(question)
        if not match or kind in seen_kinds:
            continue
        seen_kinds.add(kind)

        if kind == "last_year":
            annotations.append(f"(most recent cohort_year: {year - 1})")
        elif kind == "this_year":
            annotations.append(f"(current cohort_year: {year})")
        elif kind == "last_term":
            prev = previous_major_term(current) if season in ("Spring", "Fall") else current
            annotations.append(f"(previous major term: {prev}, {term_season(prev)} {term_year(prev)})")
        elif kind == "this_term":
            annotations.append(f"(current term: {current}, {season} {year})")
        elif kind == "past_n_years":
            n = int(match.group(1))
            annotations.append(f"(cohort_years {year - n}-{year})")
        elif kind == "recent":
            annotations.append(f"(data available through: {current}, {season} {year})")

    if not annotations:
        return question

    return f"{question} {' '.join(annotations)}"
