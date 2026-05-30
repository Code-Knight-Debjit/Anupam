"""
rag/chunker.py
──────────────
Splits raw text into overlapping chunks optimized for embedding retrieval.

Strategy:
  - Target 400 tokens per chunk (fits well in MiniLM-L6 384-dim space)
  - 50-token overlap between chunks → preserves context at boundaries
  - Sentence-aware splitting → never cuts mid-sentence when possible
  - Supports .txt, .pdf, .json input formats
"""

import re
import json
import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Chunk tuning parameters
CHUNK_SIZE    = 400   # target tokens per chunk
CHUNK_OVERLAP = 50    # token overlap between adjacent chunks
WORDS_PER_TOKEN = 0.75  # rough approximation (1 token ≈ 0.75 words for English)


def _approx_tokens(text: str) -> int:
    """Approximate token count using word count heuristic."""
    return int(len(text.split()) / WORDS_PER_TOKEN)


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences using punctuation boundaries."""
    # Split on ., !, ? followed by whitespace + capital letter
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z\-\d"])', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into overlapping chunks of approximately chunk_size tokens.

    Algorithm:
      1. Split into sentences
      2. Greedily accumulate sentences until chunk_size is reached
      3. Start next chunk from (current_pos - overlap) sentences back

    Args:
        text:       Raw input text.
        chunk_size: Target chunk size in tokens.
        overlap:    Token overlap between chunks.

    Returns:
        List of text chunk strings.
    """
    if not text or not text.strip():
        return []

    sentences = _split_into_sentences(text)
    if not sentences:
        return [text.strip()]

    chunks = []
    i = 0

    while i < len(sentences):
        current_chunk_sentences = []
        current_tokens = 0
        j = i

        while j < len(sentences):
            sent_tokens = _approx_tokens(sentences[j])
            if current_tokens + sent_tokens > chunk_size and current_chunk_sentences:
                break
            current_chunk_sentences.append(sentences[j])
            current_tokens += sent_tokens
            j += 1

        if not current_chunk_sentences:
            # Single sentence exceeds chunk_size — include it anyway
            current_chunk_sentences = [sentences[i]]
            j = i + 1

        chunk = " ".join(current_chunk_sentences).strip()
        if chunk:
            chunks.append(chunk)

        # Move pointer back by overlap amount
        overlap_tokens = 0
        step_back = 0
        for k in range(len(current_chunk_sentences) - 1, -1, -1):
            overlap_tokens += _approx_tokens(current_chunk_sentences[k])
            step_back += 1
            if overlap_tokens >= overlap:
                break

        next_i = j - step_back
        if next_i <= i:
            # If overlap would keep us on the same sentence window, force progress.
            next_i = j

        i = next_i

    # Deduplicate adjacent near-identical chunks
    unique_chunks = []
    for chunk in chunks:
        if not unique_chunks or chunk != unique_chunks[-1]:
            unique_chunks.append(chunk)

    return unique_chunks


# ─────────────────────────────────────────────
# FILE LOADERS
# ─────────────────────────────────────────────

def load_txt(filepath: str) -> Tuple[str, Dict]:
    """Load a plain text file."""
    path = Path(filepath)
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text, {"source": path.name, "type": "txt"}


def load_pdf(filepath: str) -> Tuple[str, Dict]:
    """
    Load a PDF file and extract all text.
    Falls back gracefully if PyPDF2 is not installed.
    """
    path = Path(filepath)
    try:
        import PyPDF2
        text_parts = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
        text = "\n\n".join(text_parts)
        return text, {"source": path.name, "type": "pdf", "pages": len(reader.pages)}
    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        return "", {"source": path.name, "type": "pdf", "error": "PyPDF2 not installed"}


def load_json(filepath: str) -> Tuple[List[Dict], Dict]:
    """
    Load a JSON file containing documents in Anupam Bearings format.

    Expected format:
    [
      {
        "title": "Document title",
        "content": "Main text content",
        "metadata": {
          "source": "website/docs/manual",
          "tags": ["faq", "product"]
        }
      },
      ...
    ]

    Also supports a single dict (auto-wrapped in list).
    """
    path = Path(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    return data, {"source": path.name, "type": "json"}


# ─────────────────────────────────────────────
# DOCUMENT → CHUNKS PIPELINE
# ─────────────────────────────────────────────

def file_to_chunks(
    filepath: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> Tuple[List[str], List[Dict]]:
    """
    Load any supported file and split into embedding-ready chunks.

    Args:
        filepath:   Path to .txt, .pdf, or .json file.
        chunk_size: Target tokens per chunk.
        overlap:    Token overlap between chunks.

    Returns:
        (chunks, metadatas) — parallel lists ready for add_documents()
    """
    path = Path(filepath)
    ext  = path.suffix.lower()

    if ext == ".txt":
        text, base_meta = load_txt(filepath)
        raw_chunks = chunk_text(text, chunk_size, overlap)
        metadatas  = [
            {**base_meta, "chunk_index": i, "chunk_count": len(raw_chunks)}
            for i in range(len(raw_chunks))
        ]
        return raw_chunks, metadatas

    elif ext == ".pdf":
        text, base_meta = load_pdf(filepath)
        if not text:
            return [], []
        raw_chunks = chunk_text(text, chunk_size, overlap)
        metadatas  = [
            {**base_meta, "chunk_index": i, "chunk_count": len(raw_chunks)}
            for i in range(len(raw_chunks))
        ]
        return raw_chunks, metadatas

    elif ext == ".json":
        records, base_meta = load_json(filepath)
        all_chunks    = []
        all_metadatas = []
        for record in records:
            title   = record.get("title", "")
            content = record.get("content", "")
            meta    = record.get("metadata", {})

            # Prepend title to content for better retrieval signal
            full_text = f"{title}\n\n{content}".strip() if title else content

            record_chunks = chunk_text(full_text, chunk_size, overlap)
            for i, chunk in enumerate(record_chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    **base_meta,
                    **meta,
                    "title": title,
                    "chunk_index": i,
                    "chunk_count": len(record_chunks),
                })
        return all_chunks, all_metadatas

    else:
        logger.warning(f"Unsupported file type: {ext}. Supported: .txt, .pdf, .json")
        return [], []


def texts_to_chunks(
    texts: List[str],
    metadatas: List[Dict] = None,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> Tuple[List[str], List[Dict]]:
    """
    Chunk a list of raw text strings (e.g. from database).

    Args:
        texts:     List of raw text strings.
        metadatas: Optional metadata per text (before chunking).
                   After chunking, chunk_index is added.

    Returns:
        (chunks, chunk_metadatas) — parallel lists.
    """
    metadatas = metadatas or [{} for _ in texts]
    all_chunks:    List[str]  = []
    all_metadatas: List[Dict] = []

    for text, meta in zip(texts, metadatas):
        chunks = chunk_text(text, chunk_size, overlap)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({**meta, "chunk_index": i, "chunk_count": len(chunks)})

    return all_chunks, all_metadatas
