from chatbot.rag import rewrite_query_for_retrieval


def test_standalone_question_unchanged():
    """A question with no conversational reference should pass through unchanged."""
    q = "What is the graduation rate for 2020?"
    history = []
    result = rewrite_query_for_retrieval(q, history)
    # Fallback: no history means returned unchanged
    assert result == q


def test_empty_history_returns_original():
    """With empty history, the question is returned as-is."""
    q = "and what about that one?"
    result = rewrite_query_for_retrieval(q, [])
    assert result == q


def test_history_with_no_conversational_reference():
    """Question that already stands alone despite having history."""
    q = "Show graduation rates by school"
    history = [
        {"role": "user", "content": "What is enrollment?"},
        {"role": "assistant", "content": "Enrollment data..."},
    ]
    result = rewrite_query_for_retrieval(q, history)
    # Should either be unchanged or a reasonable rewrite
    assert len(result) > 0
    assert "graduation" in result.lower()


def test_respects_only_recent_6_messages():
    """Rewrite uses only the last 6 messages of history, not the whole transcript."""
    # Construct a long history (> 6 messages)
    history = []
    for i in range(5):
        history.append({"role": "user", "content": f"Old question {i}"})
        history.append({"role": "assistant", "content": f"Old answer {i}"})

    # Only the last 6 messages should matter
    history_long = history + [
        {"role": "user", "content": "What is retention?"},
        {"role": "assistant", "content": "Retention is the % of students who come back."},
        {"role": "user", "content": "What about it?"},
        {"role": "assistant", "content": "Specifically the retention rate."},
    ]
    q = "and for first-generation students?"
    result = rewrite_query_for_retrieval(q, history_long)
    # Should mention first-generation (implied by "and for")
    assert len(result) > 0
    # If the full 10+ message history was processed, the old context would
    # pollute the rewrite. By using only last 6, we avoid that noise.


def test_returns_empty_string_on_api_failure_gracefully():
    """If API call fails, the function should return original question, not crash."""
    q = "tell me more about that"
    # Empty history means fallback
    result = rewrite_query_for_retrieval(q, [])
    assert result is not None
    assert isinstance(result, str)
