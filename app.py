"""
NJIT AI Analytics Chatbot — Streamlit Web UI

Run: streamlit run app.py
"""

import streamlit as st
from pathlib import Path
import tempfile

from chatbot.snowflake_client import test_connection
from chatbot.sql_generator import answer_sql_question
from chatbot.rag import load_document, retrieve, answer_rag_question, list_loaded_docs, doc_count, rewrite_query_for_retrieval
from chatbot.query_classifier import classify
from chatbot.conversation import ConversationHistory
from chatbot import schema_context
from chatbot import chart_helper

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NJIT Analytics Chatbot",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global font size increase via CSS ─────────────────────────────────────────
st.markdown("""
<style>
    /* Main content font size */
    .main .block-container {
        font-size: 18px;
    }
    /* Chat messages */
    [data-testid="stChatMessage"] {
        font-size: 18px;
    }
    /* Chat message text */
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] span {
        font-size: 18px !important;
        line-height: 1.7;
    }
    /* Title */
    h1 { font-size: 2.4rem !important; }
    /* Subtitles */
    h2 { font-size: 1.8rem !important; }
    h3 { font-size: 1.5rem !important; }
    /* Caption / subtext */
    .stCaption, [data-testid="stCaptionContainer"] {
        font-size: 15px !important;
    }
    /* Sidebar text */
    [data-testid="stSidebar"] {
        font-size: 16px;
    }
    /* Chat input box */
    [data-testid="stChatInput"] textarea {
        font-size: 17px !important;
    }
    /* Expander labels */
    .streamlit-expanderHeader {
        font-size: 16px !important;
    }
    /* Dataframe */
    .dataframe { font-size: 15px !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = ConversationHistory()
if "messages_display" not in st.session_state:
    st.session_state.messages_display = []

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("njit_logo_0-removebg-preview.png",
             width=160, use_container_width=False)
    st.markdown("## NJIT Analytics Assistant")
    st.markdown("Ask questions about student enrollment, graduation rates, and retention.")

    st.divider()

    # Connection status
    st.markdown("### 🔌 Connection")
    if test_connection():
        st.success("Snowflake: Connected ✅")
    else:
        st.error("Snowflake: Not connected ❌")
        st.info("Check your .env file for Snowflake credentials.")

    st.divider()

    # Document upload for RAG
    st.markdown("### 📄 Upload Documents (RAG)")
    st.caption("Upload PDFs to answer questions from documents.")
    uploaded = st.file_uploader(
        "Upload PDF or text file",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        key="doc_uploader",
    )
    if uploaded:
        for f in uploaded:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix) as tmp:
                tmp.write(f.getbuffer())
                tmp_path = tmp.name
            with st.spinner(f"Indexing {f.name}..."):
                try:
                    n = load_document(tmp_path, source_name=f.name)
                    st.success(f"✅ {f.name}: {n} chunks indexed")
                except Exception as e:
                    st.error(f"❌ {f.name}: {e}")

    loaded = list_loaded_docs()
    if loaded:
        st.markdown(f"**Loaded docs ({doc_count()} chunks):**")
        for doc in loaded:
            st.caption(f"• {doc}")

    st.divider()

    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.history.clear()
        st.session_state.messages_display = []
        st.rerun()

    if st.button("🔄 Reload schema context", use_container_width=True):
        schema_context.reload_context()
        st.success("Schema context reloaded from disk.")

# ── Main chat area ─────────────────────────────────────────────────────────────
st.title("🎓 NJIT Analytics Assistant")
st.caption(
    "Ask me anything about NJIT student enrollment, graduation rates, "
    "retention rates, and Pell-eligible student trends."
)

# Render existing messages
for i, msg in enumerate(st.session_state.messages_display):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart_fig") is not None:
            st.plotly_chart(msg["chart_fig"], use_container_width=True, key=f"chart_history_{i}")
        else:
            if msg.get("sql"):
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(msg["sql"], language="sql")
            if msg.get("dataframe") is not None and not msg["dataframe"].empty:
                with st.expander("📊 Query Results", expanded=False):
                    st.dataframe(msg["dataframe"], use_container_width=True)

# Chat input
user_input = st.chat_input("Ask a question about NJIT student data...")

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages_display.append({"role": "user", "content": user_input})

    route = classify(user_input, has_documents=doc_count() > 0)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            sql = None
            df  = None
            resolved_question = None

            if route == "clarify":
                answer = (
                    "Could you provide more detail? For example:\n"
                    "- Which school or program are you asking about?\n"
                    "- Which year or semester?\n"
                    "- Are you looking for graduation rates, retention rates, or enrollment counts?"
                )

            elif route == "rag":
                rewritten = rewrite_query_for_retrieval(user_input, st.session_state.history.to_api_format())
                chunks = retrieve(rewritten)
                answer = answer_rag_question(user_input, chunks)

            elif route == "both":
                result            = answer_sql_question(user_input, st.session_state.history)
                sql               = result["sql"]
                df                = result["dataframe"]
                answer            = result["answer"]
                resolved_question = result.get("resolved_question")
                rewritten = rewrite_query_for_retrieval(user_input, st.session_state.history.to_api_format())
                chunks    = retrieve(rewritten)
                doc_ans   = answer_rag_question(user_input, chunks) if chunks else ""
                if doc_ans:
                    answer += f"\n\n**From documents:** {doc_ans}"

            else:  # sql
                result            = answer_sql_question(user_input, st.session_state.history)
                sql               = result["sql"]
                df                = result["dataframe"]
                answer            = result["answer"]
                resolved_question = result.get("resolved_question")
                if result.get("error"):
                    answer = f"⚠️ {answer}"

        wants_chart = chart_helper.wants_chart(user_input)
        chart_fig   = None
        if df is not None and not df.empty and wants_chart and chart_helper.has_chartable_shape(df):
            chart_fig = chart_helper.build_chart(df, question=user_input)

        st.markdown(answer)
        if chart_fig is not None:
            # Chart requests: show only the chart + explanation, skip the
            # SQL/table expanders to keep the response focused on the visual.
            st.plotly_chart(chart_fig, use_container_width=True, key=f"chart_live_{len(st.session_state.messages_display)}")
        else:
            if sql:
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(sql, language="sql")
            if df is not None and not df.empty:
                with st.expander("📊 Query Results", expanded=False):
                    st.dataframe(df, use_container_width=True)

    st.session_state.history.add_user(user_input)
    st.session_state.history.add_assistant(answer)
    st.session_state.messages_display.append({
        "role": "assistant",
        "content": answer,
        "sql": sql,
        "dataframe": df,
        "resolved_question": resolved_question,
        "chart_fig": chart_fig,
    })
