"""
rag/retriever.py
────────────────
FAISS-based vector store for document retrieval.

Architecture decisions:
  - IndexFlatIP  →  exact cosine search (no approximation, perfect for <100k docs)
  - JSON sidecar → stores chunk text + metadata alongside the binary index
  - Pickle-free  → JSON is human-readable and safe
  - Thread-safe  → index is rebuilt atomically using a temp file

Index files (stored in settings.RAG_INDEX_DIR):
  faiss_index.bin   — binary FAISS index
  documents.json    — parallel array of {text, metadata} for each vector
"""

import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# ── Thread lock for index writes (one writer at a time)
_write_lock = Lock()


def _get_index_dir() -> Path:
    """Return the configured index directory, creating it if needed."""
    try:
        from django.conf import settings
        idx_dir = Path(getattr(settings, "RAG_INDEX_DIR", "data/faiss_index"))
    except Exception:
        idx_dir = Path("data/faiss_index")
    idx_dir.mkdir(parents=True, exist_ok=True)
    return idx_dir


def _index_path() -> Path:
    return _get_index_dir() / "faiss_index.bin"


def _docs_path() -> Path:
    return _get_index_dir() / "documents.json"


# ─────────────────────────────────────────────
# INDEX CREATION
# ─────────────────────────────────────────────

def create_index(embedding_dim: int = 384):
    """
    Create a brand-new empty FAISS inner-product index.
    (Inner product on L2-normalized vectors == cosine similarity)

    Args:
        embedding_dim: Must match your embedding model output dimension.
    """
    import faiss
    index = faiss.IndexFlatIP(embedding_dim)
    logger.info(f"Created new FAISS IndexFlatIP (dim={embedding_dim})")
    return index


def save_index(index, documents: List[Dict[str, Any]]) -> None:
    """
    Atomically save FAISS index + document metadata to disk.

    Uses a temp file + rename to avoid corruption if interrupted.
    """
    import faiss
    with _write_lock:
        idx_p   = _index_path()
        docs_p  = _docs_path()
        tmp_idx  = str(idx_p) + ".tmp"
        tmp_docs = str(docs_p) + ".tmp"

        faiss.write_index(index, tmp_idx)
        with open(tmp_docs, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)

        os.replace(tmp_idx,  str(idx_p))
        os.replace(tmp_docs, str(docs_p))

    logger.info(f"Saved FAISS index ({index.ntotal} vectors) → {idx_p}")


def load_index() -> Tuple[Any, List[Dict[str, Any]]]:
    """
    Load FAISS index + document metadata from disk.

    Returns:
        (faiss_index, documents_list)
        documents_list[i] corresponds to vector i in the index.

    Raises:
        FileNotFoundError if index has not been built yet.
    """
    import faiss
    idx_p  = _index_path()
    docs_p = _docs_path()

    if not idx_p.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {idx_p}. "
            "Run: python manage.py ingest_rag_data"
        )

    index = faiss.read_index(str(idx_p))
    with open(docs_p, "r", encoding="utf-8") as f:
        documents = json.load(f)

    logger.info(f"Loaded FAISS index with {index.ntotal} vectors")
    return index, documents


def index_exists() -> bool:
    """Return True if a FAISS index has been built and saved."""
    return _index_path().exists()


# ─────────────────────────────────────────────
# DOCUMENT INGESTION
# ─────────────────────────────────────────────

def add_documents(
    chunks: List[str],
    metadatas: Optional[List[Dict[str, Any]]] = None,
    rebuild: bool = False,
) -> int:
    """
    Add text chunks to the FAISS index (appends or rebuilds).

    Args:
        chunks:    List of text strings (each = one FAISS vector)
        metadatas: Optional list of dicts, same length as chunks.
                   e.g. [{"source": "faq.txt", "tags": ["product"]}]
        rebuild:   If True, wipe existing index and start fresh.
                   If False (default), append to existing index.

    Returns:
        Total number of vectors now in the index.

    Example JSON input format:
    {
        "title": "Tapered Roller Bearings",
        "content": "Timken tapered roller bearings are designed for...",
        "metadata": {
            "source": "catalogue",
            "tags": ["product", "bearing"]
        }
    }
    """
    from rag.embeddings import embed_texts, get_embedding_dim

    if not chunks:
        logger.warning("add_documents called with empty chunks list")
        return 0

    metadatas = metadatas or [{} for _ in chunks]
    assert len(chunks) == len(metadatas), "chunks and metadatas must be same length"

    # Generate embeddings
    logger.info(f"Generating embeddings for {len(chunks)} chunks…")
    embeddings = embed_texts(chunks)

    with _write_lock:
        if rebuild or not index_exists():
            # Start fresh
            index = create_index(get_embedding_dim())
            existing_docs: List[Dict] = []
        else:
            # Load existing and append
            index, existing_docs = load_index()

        # Build document records
        new_docs = [
            {"text": chunk, "metadata": meta}
            for chunk, meta in zip(chunks, metadatas)
        ]

        # Add to FAISS
        index.add(embeddings)
        all_docs = existing_docs + new_docs

    # Save (outside write_lock to minimize lock duration)
    save_index(index, all_docs)
    logger.info(f"Index now contains {index.ntotal} vectors total.")
    return index.ntotal


# ─────────────────────────────────────────────
# RETRIEVAL
# ─────────────────────────────────────────────

def search(
    query_embedding: np.ndarray,
    top_k: int = 5,
    score_threshold: float = 0.25,
) -> List[Dict[str, Any]]:
    """
    Search the FAISS index for the top-k most relevant chunks.

    Args:
        query_embedding: Shape (1, dim), L2-normalized float32 array.
        top_k:           Max number of results to return.
        score_threshold: Minimum cosine similarity score (0–1).
                         Chunks below this are filtered out.

    Returns:
        List of dicts: [{text, metadata, score}, ...]
        Sorted by descending relevance score.
    """
    if not index_exists():
        logger.warning("search() called but no FAISS index exists yet.")
        return []

    index, documents = load_index()

    if index.ntotal == 0:
        return []

    k = min(top_k, index.ntotal)
    scores, indices = index.search(query_embedding, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue  # FAISS returns -1 for empty slots
        if float(score) < score_threshold:
            continue  # below relevance threshold
        results.append({
            "text":     documents[idx]["text"],
            "metadata": documents[idx].get("metadata", {}),
            "score":    float(score),
        })

    return results


def retrieve(query: str, top_k: int = 5, score_threshold: float = 0.25) -> List[Dict]:
    """
    High-level retrieval: embed query → search → return top-k chunks.

    Args:
        query:           User's question string.
        top_k:           How many chunks to retrieve.
        score_threshold: Cosine similarity cutoff.

    Returns:
        List of relevant chunk dicts with text, metadata, score.
    """
    from rag.embeddings import embed_query
    query_vec = embed_query(query)
    return search(query_vec, top_k=top_k, score_threshold=score_threshold)


def get_index_stats() -> Dict[str, Any]:
    """Return stats about the current FAISS index."""
    if not index_exists():
        return {"exists": False, "total_vectors": 0}
    try:
        index, documents = load_index()
        sources = list({d["metadata"].get("source", "unknown") for d in documents})
        return {
            "exists": True,
            "total_vectors": index.ntotal,
            "total_documents": len(documents),
            "sources": sources,
            "index_path": str(_index_path()),
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}
