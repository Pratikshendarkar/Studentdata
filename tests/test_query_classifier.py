from chatbot.query_classifier import classify


def test_explicit_sql_question():
    assert classify("What is the graduation rate for 2020?") == "sql"


def test_explicit_rag_question_pdf():
    assert classify("What does the pdf say about the methodology?") == "rag"


def test_rag_question_the_file():
    assert classify("Explain the scenario mentioned in the file") == "rag"


def test_rag_question_the_document():
    assert classify("Summarize the document for me") == "rag"


def test_both_sql_and_rag_keywords():
    result = classify("What does the report say about the graduation rate methodology?")
    assert result == "both"


def test_very_short_question_is_clarify():
    assert classify("tell me more") == "clarify"


def test_ambiguous_question_no_documents_defaults_sql():
    assert classify("Can you tell me more about this particular topic?", has_documents=False) == "sql"


def test_ambiguous_question_with_documents_defaults_rag():
    assert classify("Can you tell me more about this particular topic?", has_documents=True) == "rag"


def test_plot_followup_routes_to_sql_even_with_documents_loaded():
    # Regression: "can you plot the graph for it" has no topical SQL
    # keyword of its own (it's a pronoun-only follow-up), so with a
    # document loaded it was previously defaulting to RAG -- a chart
    # request should always be treated as a data/SQL question.
    assert classify("can you plot the graph for it", has_documents=True) == "sql"
    assert classify("chart this for me", has_documents=True) == "sql"
    assert classify("visualize it", has_documents=False) == "sql"
