"""
RAG module using google-genai SDK (Gemini gemini-3.1-flash-lite).
Loads PDF/text docs, embeds with sentence-transformers, stores in ChromaDB.

KEY FEATURES:
- Document ingestion: PDFs and text files chunked to 800 chars with 100-char overlap
- Persistent storage: ChromaDB on disk (survives app restarts)
- Query rewriting: rewrite_query_for_retrieval() uses conversation history to resolve
  conversational references (e.g., "and what about that one?") into standalone queries
  before embedding, so follow-up questions don't lose context
- Retrieval: top-6 chunks (cosine similarity) fetched for each rewritten query
- Graceful fallback: if query rewriting fails or no docs exist, the chatbot returns
  a clear message rather than hallucinating answers
"""

import os
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client    = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL      = "gemini-3.1-flash-lite"
DOCS_DIR   = Path(__file__).parent.parent / "docs"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"

_vectorstore = None
_embedder    = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _vectorstore = client.get_or_create_collection(
            name="njit_docs",
            metadata={"hnsw:space": "cosine"},
        )
    return _vectorstore


def load_document(file_path, source_name: str | None = None) -> int:
    """
    Load PDF or text into ChromaDB. Returns chunk count.

    `source_name` is the name to record/dedup by (e.g. the original uploaded
    filename) -- defaults to the file_path's own name if not given. This
    matters because callers (e.g. app.py's uploader) often pass a temp file
    path whose random name would otherwise break both the sidebar's
    "loaded docs" display and the dedup-on-re-upload check below.
    """
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Not found: {path}")

    source = source_name or path.name

    loader = PyPDFLoader(str(path)) if path.suffix.lower() == ".pdf" \
             else TextLoader(str(path), encoding="utf-8")
    docs   = loader.load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    ).split_documents(docs)

    if not chunks:
        return 0

    texts      = [c.page_content for c in chunks]
    embeddings = _get_embedder().encode(texts).tolist()
    collection = _get_vectorstore()
    ids        = [f"{Path(source).stem}_{i}" for i in range(len(texts))]

    try:
        existing = collection.get(where={"source": source})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    collection.add(
        documents=texts, embeddings=embeddings, ids=ids,
        metadatas=[{"source": source, "chunk": i} for i in range(len(texts))],
    )
    return len(texts)


def rewrite_query_for_retrieval(question: str, history_messages: list[dict]) -> str:
    """
    Resolve conversational references ("the second point", "what about that
    one") into a standalone query before embedding it for retrieval.

    Retrieval otherwise has no memory: each question is embedded in
    isolation, so a follow-up that only makes sense against the prior turn
    retrieves the wrong (or no) chunks. `history_messages` is the last few
    turns in {"role", "content"} form (see ConversationHistory.to_api_format);
    only the most recent 6 messages (~3 user/assistant pairs) are used so the
    rewrite prompt stays cheap and focused on immediate context, not the
    whole conversation.

    Falls back to the original question unchanged if rewriting fails or the
    model returns something empty/degenerate, so a rewrite-step failure never
    blocks retrieval outright.
    """
    recent = history_messages[-6:]
    if not recent:
        return question

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    config = types.GenerateContentConfig(
        system_instruction=(
            "Rewrite the user's latest question into a standalone question "
            "that makes sense without the conversation history, by resolving "
            "any references to earlier turns (e.g. 'the second point', 'that "
            "one', 'what about X'). Preserve the original meaning and intent "
            "exactly. Output ONLY the rewritten question, nothing else. If "
            "the question is already standalone, return it unchanged."
        ),
        max_output_tokens=200,
        temperature=0.0,
    )
    try:
        resp = _client.models.generate_content(
            model=MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text=f"Conversation so far:\n{transcript}\n\n"
                         f"Latest question: {question}"
                )]
            )],
            config=config,
        )
        rewritten = (resp.text or "").strip()
        return rewritten if rewritten else question
    except Exception:
        return question


def retrieve(query: str, top_k: int = 6) -> list[str]:
    collection = _get_vectorstore()
    if collection.count() == 0:
        return []
    q_emb   = _get_embedder().encode([query]).tolist()
    results = collection.query(
        query_embeddings=q_emb,
        n_results=min(top_k, collection.count()),
    )
    return results["documents"][0] if results["documents"] else []


def answer_rag_question(question: str, context_chunks: list[str]) -> str:
    if not context_chunks:
        return (
            "I don't have any documents loaded. "
            "Please upload a PDF using the sidebar file uploader."
        )
    context = "\n\n---\n\n".join(context_chunks)
    config  = types.GenerateContentConfig(
        system_instruction=(
            "You are an NJIT Analytics Assistant. Answer the user's question "
            "using ONLY the document excerpts provided. If the answer is not "
            "in the excerpts, say so clearly. Be concise and accurate."
        ),
        max_output_tokens=1024,
        temperature=0.2,
    )
    resp = _client.models.generate_content(
        model=MODEL,
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(
                text=f"Document excerpts:\n\n{context}\n\nQuestion: {question}"
            )]
        )],
        config=config,
    )
    return resp.text


def list_loaded_docs() -> list[str]:
    try:
        collection = _get_vectorstore()
        if collection.count() == 0:
            return []
        return sorted({m["source"] for m in collection.get()["metadatas"]})
    except Exception:
        return []


def doc_count() -> int:
    try:
        return _get_vectorstore().count()
    except Exception:
        return 0
