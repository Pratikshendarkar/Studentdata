"""
RAG module using google-genai SDK (Gemini gemini-3.5-flash).
Loads PDF/text docs, embeds with sentence-transformers, stores in ChromaDB.
"""

import os
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client    = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL      = "gemini-3.5-flash"
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


def load_document(file_path) -> int:
    """Load PDF or text into ChromaDB. Returns chunk count."""
    from langchain_community.document_loaders import PyPDFLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Not found: {path}")

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
    ids        = [f"{path.stem}_{i}" for i in range(len(texts))]

    try:
        existing = collection.get(where={"source": path.name})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    collection.add(
        documents=texts, embeddings=embeddings, ids=ids,
        metadatas=[{"source": path.name, "chunk": i} for i in range(len(texts))],
    )
    return len(texts)


def retrieve(query: str, top_k: int = 5) -> list[str]:
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
