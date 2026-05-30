"""
chatbot/tasks.py
────────────────
Celery tasks wrapping the full RAG pipeline.

Why async tasks?
  - HTTP request returns immediately with a task_id
  - LLM call (2-20s) runs in background worker
  - Frontend polls /api/chat/result/<task_id>/ for the answer
  - Redis caches identical queries for 1 hour → instant repeat answers
  - Semaphore in llm_client.py limits to 4 concurrent LLM calls

Flow:
  POST /api/chat/       → enqueue task → return {task_id}
  GET  /api/chat/result/<id>/ → return {status, reply} when ready
"""

import hashlib
import logging
import json

from celery import shared_task

logger = logging.getLogger(__name__)

# ── Cache TTL: 1 hour for repeated identical queries
CACHE_TTL = 3600

# ── Top-k chunks to retrieve from FAISS
RAG_TOP_K = 5

# ── Minimum relevance score to include a chunk
RAG_SCORE_THRESHOLD = 0.22


def _cache_key(query: str, history_hash: str) -> str:
    """
    Build a Redis cache key from query + conversation history.
    Include history_hash so same question in different contexts isn't confused.
    """
    raw = f"rag_chat:{query.lower().strip()}:{history_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _hash_history(history: list) -> str:
    """Short hash of conversation history for cache keying."""
    serialized = json.dumps(history[-4:], sort_keys=True)  # last 2 turns only
    return hashlib.md5(serialized.encode()).hexdigest()[:8]


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=3,
    name="chatbot.tasks.run_rag_pipeline",
    time_limit=300,       # hard kill after 5 min (Ollama on CPU can need 2+ min)
    soft_time_limit=240,  # raises SoftTimeLimitExceeded at 4 min
)
def run_rag_pipeline(self, query: str, history: list = None, session_id: str = "") -> dict:
    """
    Full RAG pipeline as a Celery task.

    Steps:
      1. Check Redis cache for identical query+context
      2. Retrieve top-k relevant chunks from FAISS
      3. Build structured prompt (system + context + history + query)
      4. Call Ollama LLM with concurrency control
      5. Cache the result
      6. Save to DB

    Args:
        query:      User's question string.
        history:    List of {"role": str, "content": str} dicts.
        session_id: Django session ID for DB storage.

    Returns:
        {"reply": str, "sources": list, "cached": bool, "chunks_found": int}
    """
    from django.core.cache import cache
    from rag.retriever import retrieve, index_exists
    from rag.prompt_builder import build_prompt, build_simple_prompt
    from rag.llm_client import call_llm
    from contact.models import ChatMessage

    history = history or []

    # ── STEP 1: Cache check ──────────────────────────────────────────────────
    history_hash = _hash_history(history)
    cache_key    = _cache_key(query, history_hash)
    cached       = cache.get(cache_key)

    if cached:
        logger.info(f"Cache HIT for query: {query[:60]}…")
        # Still save to DB so dashboard shows it
        if session_id:
            _save_to_db(session_id, "user", query)
            _save_to_db(session_id, "assistant", cached["reply"])
        return {**cached, "cached": True}

    # ── STEP 2: Retrieve relevant chunks ─────────────────────────────────────
    sources      = []
    chunks_found = 0
    prompt       = ""

    try:
        if index_exists():
            retrieved = retrieve(query, top_k=RAG_TOP_K, score_threshold=RAG_SCORE_THRESHOLD)
            chunks_found = len(retrieved)
            sources = [
                {
                    "source": c.get("metadata", {}).get("source", "knowledge base"),
                    "score":  round(c.get("score", 0), 3),
                }
                for c in retrieved
            ]
            logger.info(f"RAG retrieved {chunks_found} chunks for: {query[:60]}")
            prompt = build_prompt(query, retrieved, history)
        else:
            logger.warning("FAISS index not found — using prompt-only mode")
            prompt = build_simple_prompt(query, history)
    except Exception as e:
        logger.error(f"Retrieval error: {e}", exc_info=True)
        prompt = build_simple_prompt(query, history)

    # ── STEP 3: Call LLM ─────────────────────────────────────────────────────
    try:
        reply = call_llm(prompt, temperature=0.3, max_tokens=512)
    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        reply = (
            "I'm having trouble right now. Please contact us directly at "
            "info@anupambearings.com or call +91-98844-00741."
        )

    # ── STEP 4: Cache the result ─────────────────────────────────────────────
    result = {
        "reply":        reply,
        "sources":      sources,
        "cached":       False,
        "chunks_found": chunks_found,
    }
    # Only cache if we got a meaningful response (not an error fallback)
    if len(reply) > 30 and "having trouble" not in reply:
        cache.set(cache_key, result, timeout=CACHE_TTL)

    # ── STEP 5: Persist to DB ────────────────────────────────────────────────
    if session_id:
        try:
            _save_to_db(session_id, "user", query)
            _save_to_db(session_id, "assistant", reply)
        except Exception as e:
            logger.warning(f"DB save failed (non-critical): {e}")

    return result


def _save_to_db(session_id: str, role: str, content: str) -> None:
    """Save a chat message to the database."""
    from contact.models import ChatMessage
    ChatMessage.objects.create(
        session_id=session_id,
        role=role,
        content=content,
    )


# ─────────────────────────────────────────────
# BACKGROUND INDEXING TASK
# ─────────────────────────────────────────────

@shared_task(
    name="chatbot.tasks.ingest_documents_task",
    time_limit=600,
)
def ingest_documents_task(
    chunks: list,
    metadatas: list = None,
    rebuild: bool = False,
) -> dict:
    """
    Background task to add documents to the FAISS index.

    Use this when ingesting large document sets so the web server
    doesn't block. Triggered by the management command or dashboard.

    Args:
        chunks:    List of text strings to index.
        metadatas: Optional list of metadata dicts.
        rebuild:   Wipe existing index and rebuild from scratch.

    Returns:
        {"success": bool, "total_vectors": int, "error": str|None}
    """
    from rag.retriever import add_documents
    try:
        total = add_documents(chunks, metadatas, rebuild=rebuild)
        logger.info(f"Background ingestion complete: {total} vectors")
        return {"success": True, "total_vectors": total, "error": None}
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}", exc_info=True)
        return {"success": False, "total_vectors": 0, "error": str(e)}


@shared_task(name="chatbot.tasks.warm_embedding_model")
def warm_embedding_model() -> dict:
    """
    Pre-load the sentence-transformer model into memory.
    Call this on worker startup to avoid cold-start latency on first query.

    Usage in celery config:
        app.send_task('chatbot.tasks.warm_embedding_model')
    """
    try:
        from rag.embeddings import embed_texts
        embed_texts(["warmup"])  # triggers lru_cache load
        logger.info("Embedding model warmed up successfully.")
        return {"success": True}
    except Exception as e:
        logger.error(f"Model warmup failed: {e}")
        return {"success": False, "error": str(e)}
