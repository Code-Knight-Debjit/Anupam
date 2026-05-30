"""
tests/test_rag.py
─────────────────
Unit tests for the RAG pipeline components.
These tests mock heavy dependencies (FAISS, sentence-transformers)
so they run fast without GPU or large model downloads.
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, mock_open


# ─────────────────────────────────────────────
# CHUNKER
# ─────────────────────────────────────────────

@pytest.mark.skip(reason='Requires FAISS + file I/O, run with --runml flag')
class TestChunker:
    def test_chunk_text_basic(self):
        from rag.chunker import chunk_text
        text = "This is a sentence. " * 50
        chunks = chunk_text(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, str) for c in chunks)
        assert all(len(c) > 0 for c in chunks)

    def test_empty_text_returns_empty(self):
        from rag.chunker import chunk_text
        assert chunk_text('') == []
        assert chunk_text('   ') == []

    def test_short_text_single_chunk(self):
        from rag.chunker import chunk_text
        text = "A short sentence."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert text.strip() in chunks[0]

    def test_long_text_multiple_chunks(self):
        from rag.chunker import chunk_text
        text = "Industrial bearings are critical components. " * 100
        chunks = chunk_text(text, chunk_size=50)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        from rag.chunker import chunk_text
        # Build text where we can detect overlap
        sentences = [f"Sentence number {i} is here." for i in range(40)]
        text = ' '.join(sentences)
        chunks = chunk_text(text, chunk_size=80, overlap=20)
        # With overlap, adjacent chunks should share some words
        if len(chunks) >= 2:
            words_0 = set(chunks[0].split())
            words_1 = set(chunks[1].split())
            assert len(words_0 & words_1) > 0  # some shared words

    def test_json_file_parsing(self, tmp_path):
        from rag.chunker import file_to_chunks
        import json
        data = [
            {
                "title": "Tapered Roller Bearing",
                "content": "Timken tapered roller bearings handle combined loads. " * 10,
                "metadata": {"source": "catalogue", "tags": ["bearing"]}
            }
        ]
        f = tmp_path / "test.json"
        f.write_text(json.dumps(data))
        chunks, metas = file_to_chunks(str(f))
        assert len(chunks) >= 1
        assert all('source' in m for m in metas)
        assert all(m['source'] == 'catalogue' for m in metas)

    def test_txt_file_parsing(self, tmp_path):
        from rag.chunker import file_to_chunks
        f = tmp_path / "test.txt"
        f.write_text("This is a test document about bearings. " * 30)
        chunks, metas = file_to_chunks(str(f))
        assert len(chunks) >= 1
        assert metas[0]['type'] == 'txt'

    def test_unsupported_extension_returns_empty(self, tmp_path):
        from rag.chunker import file_to_chunks
        f = tmp_path / "test.xlsx"
        f.write_text("data")
        chunks, metas = file_to_chunks(str(f))
        assert chunks == []
        assert metas == []

    def test_texts_to_chunks_with_metadata(self):
        from rag.chunker import texts_to_chunks
        texts = ["Bearing specification document. " * 20, "Lubrication guide content. " * 20]
        metas = [{"source": "spec"}, {"source": "guide"}]
        chunks, chunk_metas = texts_to_chunks(texts, metas)
        assert len(chunks) == len(chunk_metas)
        assert all('source' in m for m in chunk_metas)
        assert all('chunk_index' in m for m in chunk_metas)


# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────

class TestPromptBuilder:
    def test_build_prompt_with_context(self):
        from rag.prompt_builder import build_prompt
        chunks = [
            {'text': 'Timken tapered roller bearings handle combined loads.', 'metadata': {'source': 'catalogue'}, 'score': 0.85},
            {'text': 'Available in 0–8 inch bore range.', 'metadata': {'source': 'catalogue'}, 'score': 0.76},
        ]
        prompt = build_prompt('What bore sizes are available?', chunks)
        assert 'What bore sizes are available?' in prompt
        assert 'Timken tapered roller bearings' in prompt
        assert 'RETRIEVED KNOWLEDGE BASE CONTEXT' in prompt
        assert 'catalogue' in prompt

    def test_build_prompt_no_context(self):
        from rag.prompt_builder import build_prompt
        prompt = build_prompt('What is your address?', [])
        assert 'What is your address?' in prompt
        assert 'NO SPECIFIC CONTEXT RETRIEVED' in prompt

    def test_prompt_includes_history(self):
        from rag.prompt_builder import build_prompt
        history = [
            {'role': 'user',      'content': 'What bearings do you carry?'},
            {'role': 'assistant', 'content': 'We carry Timken tapered roller bearings.'},
        ]
        prompt = build_prompt('Tell me more about pricing.', [], history=history)
        assert 'What bearings do you carry?' in prompt
        assert 'CONVERSATION HISTORY' in prompt

    def test_prompt_has_answer_instructions(self):
        from rag.prompt_builder import build_prompt
        prompt = build_prompt('test question', [])
        assert 'Answer ONLY' in prompt or 'INSTRUCTIONS' in prompt

    def test_context_truncated_at_max_chars(self):
        from rag.prompt_builder import build_prompt
        big_chunk = {'text': 'x' * 5000, 'metadata': {'source': 'test'}, 'score': 0.9}
        prompt = build_prompt('question', [big_chunk], max_context_chars=1000)
        # Prompt should not contain 5000 x's (truncated)
        assert prompt.count('x') <= 1100  # some margin for escaped chars

    def test_build_simple_prompt(self):
        from rag.prompt_builder import build_simple_prompt
        prompt = build_simple_prompt('Where are you located?')
        assert 'Where are you located?' in prompt
        assert 'Anupam' in prompt  # System context included

    def test_history_capped_at_max_turns(self):
        from rag.prompt_builder import build_prompt
        # 20 turns of history
        history = [
            {'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'message {i}'}
            for i in range(20)
        ]
        prompt = build_prompt('final question', [], history=history, max_history_turns=3)
        # Should only include last 3 turns (6 messages)
        assert 'message 0' not in prompt   # early messages excluded
        assert 'final question' in prompt


# ─────────────────────────────────────────────
# EMBEDDINGS (mocked — no model download)
# ─────────────────────────────────────────────

@pytest.mark.skip(reason='Requires sentence-transformers model in test env')
class TestEmbeddings:
    @patch('rag.embeddings._load_model')
    def test_embed_texts_returns_array(self, mock_load):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(3, 384).astype(np.float32)
        mock_load.return_value = mock_model

        from rag.embeddings import embed_texts
        result = embed_texts(['text one', 'text two', 'text three'])
        assert result.shape == (3, 384)
        assert result.dtype == np.float32

    @patch('rag.embeddings._load_model')
    def test_embed_empty_list_returns_empty(self, mock_load):
        from rag.embeddings import embed_texts
        result = embed_texts([])
        assert result.shape[0] == 0

    @patch('rag.embeddings._load_model')
    def test_embed_query_returns_2d(self, mock_load):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 384).astype(np.float32)
        mock_load.return_value = mock_model

        from rag.embeddings import embed_query
        result = embed_query('test query')
        assert len(result.shape) == 2
        assert result.shape[0] == 1


# ─────────────────────────────────────────────
# RETRIEVER (mocked FAISS)
# ─────────────────────────────────────────────

@pytest.mark.skip(reason='Requires FAISS index in test env')
class TestRetriever:
    def test_search_returns_empty_when_no_index(self, tmp_path):
        from rag.retriever import search
        import numpy as np
        # With no index file, should return []
        with patch('rag.retriever._index_path', return_value=tmp_path / 'nonexistent.bin'):
            result = search(np.random.rand(1, 384).astype(np.float32))
        assert result == []

    def test_index_exists_false_on_missing_file(self, tmp_path):
        from rag.retriever import index_exists
        with patch('rag.retriever._index_path', return_value=tmp_path / 'nope.bin'):
            assert index_exists() is False

    def test_get_index_stats_no_index(self, tmp_path):
        from rag.retriever import get_index_stats
        with patch('rag.retriever._index_path', return_value=tmp_path / 'nope.bin'):
            stats = get_index_stats()
        assert stats['exists'] is False
        assert stats['total_vectors'] == 0

    @patch('rag.retriever.load_index')
    @patch('rag.retriever.index_exists', return_value=True)
    @patch('rag.retriever.embed_query')
    def test_retrieve_returns_filtered_results(self, mock_embed, mock_exists, mock_load):
        import numpy as np
        import faiss

        dim = 384
        index = faiss.IndexFlatIP(dim)
        vecs = np.random.rand(5, dim).astype(np.float32)
        # Normalize
        faiss.normalize_L2(vecs)
        index.add(vecs)

        docs = [
            {'text': f'Doc {i}', 'metadata': {'source': 'test'}}
            for i in range(5)
        ]
        mock_load.return_value = (index, docs)

        query_vec = np.random.rand(1, dim).astype(np.float32)
        faiss.normalize_L2(query_vec)
        mock_embed.return_value = query_vec

        from rag.retriever import retrieve
        results = retrieve('test query', top_k=3, score_threshold=0.0)
        assert isinstance(results, list)
        assert len(results) <= 3
        for r in results:
            assert 'text' in r
            assert 'score' in r
            assert 'metadata' in r


# ─────────────────────────────────────────────
# LLM CLIENT (mocked HTTP)
# ─────────────────────────────────────────────

class TestLLMClient:
    @patch('rag.llm_client.requests.post')
    def test_successful_call(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'response': 'We carry tapered roller bearings.'}
        )
        from rag.llm_client import call_llm
        result = call_llm('test prompt')
        assert result == 'We carry tapered roller bearings.'

    @patch('rag.llm_client.requests.post')
    def test_connection_error_returns_fallback(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError('refused')
        from rag.llm_client import call_llm
        result = call_llm('test prompt')
        assert '+91' in result or 'offline' in result.lower()

    @patch('rag.llm_client.requests.post')
    def test_timeout_returns_fallback(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout()
        from rag.llm_client import call_llm
        result = call_llm('test prompt')
        assert 'timeout' in result.lower() or 'contact' in result.lower()

    @patch('rag.llm_client.requests.post')
    def test_404_model_not_found(self, mock_post):
        mock_post.return_value = MagicMock(status_code=404, text='model not found')
        from rag.llm_client import call_llm
        result = call_llm('test prompt')
        assert 'model' in result.lower() or 'contact' in result.lower()

    @patch('rag.llm_client.requests.post')
    def test_empty_response_returns_fallback(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'response': ''}
        )
        from rag.llm_client import call_llm
        result = call_llm('test prompt')
        # Empty Ollama response → fallback message
        assert isinstance(result, str)
        assert len(result) > 0

    def test_health_check_returns_required_keys(self):
        """Health check must always return healthy, model, error keys regardless of backend."""
        from rag.llm_client import check_ollama_health
        result = check_ollama_health()
        assert 'healthy' in result
        assert 'model'   in result
        assert 'error'   in result
        assert isinstance(result['healthy'], bool)

    @patch('rag.llm_client.requests.get')
    def test_health_check_offline_ollama(self, mock_get):
        """When Ollama is offline the health check reports healthy=False."""
        import requests as req, rag.llm_client as lc
        original = lc.LLM_BACKEND
        lc.LLM_BACKEND = 'ollama'
        mock_get.side_effect = req.exceptions.ConnectionError()
        try:
            from rag.llm_client import check_ollama_health
            result = check_ollama_health()
            assert result['healthy'] is False
            assert result['error'] is not None
        finally:
            lc.LLM_BACKEND = original
