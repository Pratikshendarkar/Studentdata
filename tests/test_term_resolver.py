import pandas as pd
import pytest

from chatbot import term_resolver


def test_term_year():
    assert term_resolver.term_year("202490") == 2024
    assert term_resolver.term_year("202410") == 2024


def test_term_season():
    assert term_resolver.term_season("202490") == "Fall"
    assert term_resolver.term_season("202410") == "Spring"
    assert term_resolver.term_season("202450") == "Summer"
    assert term_resolver.term_season("202495") == "Winter"


def test_shift_year_round_trip():
    original = "202490"
    shifted = term_resolver.shift_year(original, 3)
    assert shifted == "202790"
    assert term_resolver.shift_year(shifted, -3) == original


def test_previous_major_term_fall_to_spring():
    assert term_resolver.previous_major_term("202490") == "202410"


def test_previous_major_term_spring_to_prior_fall():
    assert term_resolver.previous_major_term("202410") == "202390"


def test_previous_major_term_rejects_non_major_term():
    with pytest.raises(ValueError):
        term_resolver.previous_major_term("202450")


@pytest.fixture(autouse=True)
def _mock_current_term(monkeypatch):
    """Pin get_current_term() to a known value for deterministic tests."""
    term_resolver.get_current_term.cache_clear()
    monkeypatch.setattr(
        term_resolver, "run_query",
        lambda sql: (pd.DataFrame([{"MAX_TERM": "202490"}]), ""),
    )
    yield
    term_resolver.get_current_term.cache_clear()


def test_get_current_term():
    assert term_resolver.get_current_term() == "202490"


def test_resolve_last_year():
    result = term_resolver.resolve_relative_terms("How many students graduated last year?")
    assert "cohort_year: 2023" in result


def test_resolve_this_year():
    result = term_resolver.resolve_relative_terms("What is the graduation rate this year?")
    assert "cohort_year: 2024" in result


def test_resolve_last_semester():
    result = term_resolver.resolve_relative_terms("What was retention last semester?")
    assert "202410" in result
    assert "Spring 2024" in result


def test_resolve_this_term():
    result = term_resolver.resolve_relative_terms("How many students enrolled this term?")
    assert "202490" in result
    assert "Fall 2024" in result


def test_resolve_past_n_years():
    result = term_resolver.resolve_relative_terms("Show enrollment trends for the past 3 years")
    assert "cohort_years 2021-2024" in result


def test_resolve_recent():
    result = term_resolver.resolve_relative_terms("What are recent graduation rates?")
    assert "202490" in result


def test_resolve_no_relative_phrase_unchanged():
    question = "What is the graduation rate for the 2018 cohort in Fall 2023?"
    assert term_resolver.resolve_relative_terms(question) == question
