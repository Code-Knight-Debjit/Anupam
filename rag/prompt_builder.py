"""
rag/prompt_builder.py
─────────────────────
Constructs the final prompt sent to Ollama by combining:
  1. System instructions  (who the bot is, how to behave)
  2. Retrieved context    (top-k chunks from FAISS)
  3. Conversation history (last N turns for multi-turn support)
  4. Current user query
"""

from typing import List, Dict, Any

SYSTEM_PROMPT = """You are Anupam Assistant, the expert AI assistant for Anupam Bearings — a certified Timken parts supplier based in India with offices in Bengaluru and Chennai.

Core company facts:
- Founder & Mentor: Mr. Anant Kumar Singh
- Timken partner
- Website: www.anupambearings.com
- Bengaluru: No. 128, Jigani Link Road, Bommasandra Industrial Area | +91-98844-00741 | sales@anupambearings.com
- Chennai: No. 3 Katchaleeswarar Pagoda Lane, Parrys | 044-4691-2265 | info@anupambearings.com

Your behaviour rules:
1. Answer ONLY from the provided context and your company knowledge above.
2. If the answer is not in the context, say exactly: "I don't have specific information on that. Please contact us at info@anupambearings.com or call +91-98844-00741."
3. Be concise, professional, and technically accurate.
4. Never invent product specs, prices, or availability.
5. Always offer to connect the user with the sales team for detailed quotes."""


def build_prompt(
    query: str,
    retrieved_chunks: List[Dict[str, Any]],
    history: List[Dict[str, str]] = None,
    max_context_chars: int = 3000,
    max_history_turns: int = 5,
) -> str:
    """
    Assemble the complete prompt string for Ollama.

    Args:
        query:             The current user question.
        retrieved_chunks:  List of dicts from retriever.retrieve()
                           Each: {"text": str, "metadata": dict, "score": float}
        history:           Previous turns as [{"role": "user"|"assistant", "content": str}]
        max_context_chars: Hard cap on retrieved context length.
        max_history_turns: How many past turns to include.

    Returns:
        Single formatted string ready to POST to Ollama /api/generate.
    """
    history = history or []

    # 1. BUILD CONTEXT SECTION
    if retrieved_chunks:
        context_parts = []
        total_chars = 0
        for i, chunk in enumerate(retrieved_chunks, 1):
            text   = chunk["text"].strip()
            source = chunk.get("metadata", {}).get("source", "knowledge base")
            score  = chunk.get("score", 0)
            if len(text) > 800:
                text = text[:800] + "..."
            entry = f"[Source {i}: {source} | relevance: {score:.2f}]\n{text}"
            if total_chars + len(entry) > max_context_chars:
                break
            context_parts.append(entry)
            total_chars += len(entry)
        context_block = "\n\n".join(context_parts)
        context_section = (
            "--- RETRIEVED KNOWLEDGE BASE CONTEXT ---\n"
            + context_block
            + "\n--- END CONTEXT ---"
        )
    else:
        context_section = (
            "--- NO SPECIFIC CONTEXT RETRIEVED ---\n"
            "Use your general knowledge about Anupam Bearings to answer."
        )

    # 2. BUILD CONVERSATION HISTORY
    history_section = ""
    if history:
        recent = history[-(max_history_turns * 2):]
        turns = []
        for msg in recent:
            role    = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if role == "user":
                turns.append(f"User: {content}")
            else:
                turns.append(f"Assistant: {content}")
        if turns:
            history_section = (
                "\n--- CONVERSATION HISTORY ---\n"
                + "\n".join(turns)
                + "\n--- END HISTORY ---\n"
            )

    # 3. ASSEMBLE FINAL PROMPT
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{context_section}\n"
        f"{history_section}\n"
        "--- INSTRUCTIONS ---\n"
        "- Answer ONLY using the context above.\n"
        "- If context is insufficient, say you don't have specific information.\n"
        "- Be concise and accurate. Do NOT make up specifications or prices.\n"
        "- If the user asks for a quote or purchase, direct them to the sales team.\n\n"
        f"User Question: {query}\n\n"
        "Assistant:"
    )
    return prompt


def build_simple_prompt(query: str, history: List[Dict[str, str]] = None) -> str:
    """
    Fallback prompt when RAG index is empty or unavailable.
    Uses only the system context + history.
    """
    return build_prompt(query=query, retrieved_chunks=[], history=history)
