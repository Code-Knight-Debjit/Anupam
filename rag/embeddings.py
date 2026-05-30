"""
rag/embeddings.py
─────────────────
Handles all embedding operations using sentence-transformers.
Model: all-MiniLM-L6-v2  (384-dim, ~80MB, very fast, great quality)

Why this model:
  - Runs entirely on CPU (no GPU needed)
  - 384 dimensions → small FAISS index
  - <100ms per query on modern hardware
  - Top-tier retrieval performance for short passages
"""

import os
import logging
import numpy as np
from typing import List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── Model name — swap here to upgrade e.g. "all-mpnet-base-v2" for better quality
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM   = 384  # must match model output; update if you change model


@lru_cache(maxsize=1)
def _load_model():
    """
    Load and cache the SentenceTransformer model.
    lru_cache(1) means it's loaded once per process — avoids reloading on every request.
    """
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info("Embedding model loaded successfully.")
    return model


def embed_texts(texts: List[str], batch_size: int = 32) -> np.ndarray:
    """
    Generate normalized L2 embeddings for a list of texts.

    Args:
        texts:      List of strings to embed
        batch_size: How many texts to process per forward pass (tune for RAM)

    Returns:
        np.ndarray of shape (len(texts), EMBEDDING_DIM), dtype float32
    """
    if not texts:
        return np.array([], dtype=np.float32).reshape(0, EMBEDDING_DIM)

    model = _load_model()

    # normalize_embeddings=True → cosine similarity == dot product
    # This is critical for FAISS IndexFlatIP (inner product search)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,   # ← key for cosine similarity
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """
    Embed a single query string.
    Returns shape (1, EMBEDDING_DIM) — ready to pass to FAISS search.
    """
    return embed_texts([query])


def get_embedding_dim() -> int:
    """Return the embedding dimension for the current model."""
    return EMBEDDING_DIM
