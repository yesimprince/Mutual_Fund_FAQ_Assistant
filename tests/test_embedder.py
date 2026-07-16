"""
Unit tests for the embedder module.

Tests cover:
- Embedding produces vectors of expected dimension (384 for BGE-small)
- All 55 chunks receive embeddings
- Query embedding includes instruction prefix and returns 384-dim vector
- Batch processing produces consistent results
- load_all_chunks reads from per-scheme JSONL files
- Edge cases (empty inputs, missing text fields)
"""

import os
import sys
import json
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.embedder import (
    load_all_chunks,
    embed_chunks,
    embed_query,
    embed_all,
    EMBEDDING_DIM,
    QUERY_INSTRUCTION_PREFIX,
    CHUNKS_DATA_DIR,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_chunks():
    """A minimal list of chunks matching the real data structure."""
    return [
        {
            "text": "HDFC Large Cap Fund Direct Growth — Key Facts: Expense Ratio: 1.04%.",
            "chunk_type": "structured_facts",
            "chunk_id": "hdfc-large-cap_structured_facts_0",
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        },
        {
            "text": "Q: What is the expense ratio of HDFC Large Cap Fund?\nA: The expense ratio is 1.04%.",
            "chunk_type": "faq",
            "chunk_id": "hdfc-large-cap_faq_0",
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        },
        {
            "text": "Scheme Overview\nScheme: HDFC Large Cap Fund\nFund House: HDFC Mutual Fund",
            "chunk_type": "section",
            "chunk_id": "hdfc-large-cap_section_0",
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        },
    ]


@pytest.fixture
def real_chunks():
    """Load all real chunks if they exist."""
    chunks_dir = os.path.normpath(CHUNKS_DATA_DIR)
    if not os.path.exists(chunks_dir):
        pytest.skip("Chunks data directory not found")

    chunks = load_all_chunks()
    if not chunks:
        pytest.skip("No chunk files found")

    return chunks


# ---------------------------------------------------------------------------
# Tests: load_all_chunks
# ---------------------------------------------------------------------------

class TestLoadAllChunks:
    """Tests for the chunk loading function."""

    def test_loads_from_real_files(self, real_chunks):
        """Should load chunks from all per-scheme JSONL files."""
        assert len(real_chunks) > 0

    def test_loads_expected_count(self, real_chunks):
        """Should load ~55 chunks from 5 scheme files."""
        assert 40 <= len(real_chunks) <= 80, (
            f"Expected ~55 chunks, got {len(real_chunks)}"
        )

    def test_each_chunk_has_text(self, real_chunks):
        """Every loaded chunk must have a non-empty text field."""
        for chunk in real_chunks:
            assert "text" in chunk, f"Missing 'text' in chunk {chunk.get('chunk_id')}"
            assert len(chunk["text"]) > 0, f"Empty text in chunk {chunk.get('chunk_id')}"

    def test_each_chunk_has_chunk_id(self, real_chunks):
        """Every loaded chunk must have a chunk_id."""
        for chunk in real_chunks:
            assert "chunk_id" in chunk, "Missing 'chunk_id' in chunk"

    def test_returns_empty_for_missing_dir(self, tmp_path, monkeypatch):
        """Should return empty list if chunks directory doesn't exist."""
        import src.ingestion.embedder as embedder_module
        monkeypatch.setattr(embedder_module, "CHUNKS_DATA_DIR", str(tmp_path / "nonexistent"))
        result = load_all_chunks()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: embed_chunks
# ---------------------------------------------------------------------------

class TestEmbedChunks:
    """Tests for the chunk embedding function."""

    def test_produces_384_dim_vectors(self, sample_chunks):
        """Embeddings must be 384-dimensional (BGE-small output)."""
        result = embed_chunks(sample_chunks)
        for chunk in result:
            assert "embedding" in chunk, f"Missing embedding for {chunk['chunk_id']}"
            assert len(chunk["embedding"]) == EMBEDDING_DIM, (
                f"Expected {EMBEDDING_DIM} dims, got {len(chunk['embedding'])} "
                f"for {chunk['chunk_id']}"
            )

    def test_embeddings_are_float_lists(self, sample_chunks):
        """Each embedding should be a list of floats."""
        result = embed_chunks(sample_chunks)
        for chunk in result:
            embedding = chunk["embedding"]
            assert isinstance(embedding, list)
            assert all(isinstance(v, float) for v in embedding)

    def test_preserves_original_fields(self, sample_chunks):
        """Embedding should not remove existing chunk fields."""
        result = embed_chunks(sample_chunks)
        for chunk in result:
            assert "text" in chunk
            assert "chunk_type" in chunk
            assert "chunk_id" in chunk
            assert "scheme_name" in chunk

    def test_different_texts_produce_different_embeddings(self, sample_chunks):
        """Different text content should produce different embedding vectors."""
        result = embed_chunks(sample_chunks)
        emb_0 = result[0]["embedding"]
        emb_1 = result[1]["embedding"]
        # They should not be identical
        assert emb_0 != emb_1

    def test_empty_input_returns_empty(self):
        """Should handle empty chunk list gracefully."""
        result = embed_chunks([])
        assert result == []

    def test_batch_size_does_not_affect_result(self, sample_chunks):
        """Different batch sizes should produce identical embeddings."""
        import copy
        chunks_batch1 = copy.deepcopy(sample_chunks)
        chunks_batch32 = copy.deepcopy(sample_chunks)

        result_batch1 = embed_chunks(chunks_batch1, batch_size=1)
        result_batch32 = embed_chunks(chunks_batch32, batch_size=32)

        for c1, c32 in zip(result_batch1, result_batch32):
            # Allow tiny floating-point differences
            for v1, v32 in zip(c1["embedding"], c32["embedding"]):
                assert abs(v1 - v32) < 1e-5, "Batch size changed embedding values"

    def test_normalized_embeddings(self, sample_chunks):
        """Embeddings should be L2-normalized (unit vectors)."""
        result = embed_chunks(sample_chunks)
        for chunk in result:
            embedding = chunk["embedding"]
            norm = sum(v ** 2 for v in embedding) ** 0.5
            assert abs(norm - 1.0) < 0.01, (
                f"Embedding not normalized: L2 norm = {norm}"
            )


# ---------------------------------------------------------------------------
# Tests: embed_query
# ---------------------------------------------------------------------------

class TestEmbedQuery:
    """Tests for the query embedding function."""

    def test_returns_384_dim_vector(self):
        """Query embedding must be 384-dimensional."""
        embedding = embed_query("What is the expense ratio?")
        assert len(embedding) == EMBEDDING_DIM

    def test_returns_float_list(self):
        """Query embedding should be a list of floats."""
        embedding = embed_query("What is the NAV?")
        assert isinstance(embedding, list)
        assert all(isinstance(v, float) for v in embedding)

    def test_different_queries_produce_different_embeddings(self):
        """Different queries should yield different embedding vectors."""
        emb_1 = embed_query("What is the expense ratio?")
        emb_2 = embed_query("How to invest in SIP?")
        assert emb_1 != emb_2

    def test_query_embedding_differs_from_document_embedding(self, sample_chunks):
        """
        Query embedding (with prefix) should differ from document embedding
        (without prefix) of the same text, confirming the prefix is applied.
        """
        text = "What is the expense ratio of HDFC Large Cap Fund?"

        # Query embedding (with instruction prefix)
        query_emb = embed_query(text)

        # Document embedding (without prefix)
        doc_chunk = [{"text": text, "chunk_id": "test"}]
        embed_chunks(doc_chunk)
        doc_emb = doc_chunk[0]["embedding"]

        # They should differ due to the instruction prefix
        diff = sum(abs(q - d) for q, d in zip(query_emb, doc_emb))
        assert diff > 0.1, (
            "Query and document embeddings are too similar — "
            "instruction prefix may not be applied"
        )

    def test_normalized_query_embedding(self):
        """Query embedding should be L2-normalized."""
        embedding = embed_query("What is the exit load?")
        norm = sum(v ** 2 for v in embedding) ** 0.5
        assert abs(norm - 1.0) < 0.01, (
            f"Query embedding not normalized: L2 norm = {norm}"
        )


# ---------------------------------------------------------------------------
# Tests: embed_all (integration)
# ---------------------------------------------------------------------------

class TestEmbedAll:
    """Integration tests for the full embedding pipeline."""

    def test_all_chunks_get_embeddings(self, real_chunks):
        """embed_all should add embeddings to all loaded chunks."""
        # We use real_chunks fixture which already loads chunks
        # Now embed them
        result = embed_chunks(real_chunks)

        for chunk in result:
            assert "embedding" in chunk, (
                f"Missing embedding for {chunk.get('chunk_id')}"
            )
            assert len(chunk["embedding"]) == EMBEDDING_DIM

    def test_total_embedded_count(self, real_chunks):
        """Should embed all ~55 chunks."""
        result = embed_chunks(real_chunks)
        with_embeddings = sum(1 for c in result if "embedding" in c)
        assert with_embeddings == len(real_chunks)
        assert 40 <= with_embeddings <= 80


# ---------------------------------------------------------------------------
# Tests: Semantic similarity sanity check
# ---------------------------------------------------------------------------

class TestSemanticSimilarity:
    """Sanity checks that embeddings capture semantic meaning."""

    def test_similar_texts_have_high_similarity(self):
        """Semantically similar texts should have high cosine similarity."""
        chunks = [
            {"text": "The expense ratio of HDFC Large Cap Fund is 1.04%.", "chunk_id": "a"},
            {"text": "HDFC Large Cap Fund charges an expense ratio of 1.04%.", "chunk_id": "b"},
            {"text": "The weather in Mumbai is hot and humid today.", "chunk_id": "c"},
        ]
        result = embed_chunks(chunks)

        # Cosine similarity (embeddings are normalized, so dot product = cosine sim)
        def cosine_sim(a, b):
            return sum(x * y for x, y in zip(a, b))

        sim_ab = cosine_sim(result[0]["embedding"], result[1]["embedding"])
        sim_ac = cosine_sim(result[0]["embedding"], result[2]["embedding"])

        # Similar texts should have higher similarity than dissimilar ones
        assert sim_ab > sim_ac, (
            f"Similar texts similarity ({sim_ab:.4f}) should be > "
            f"dissimilar texts similarity ({sim_ac:.4f})"
        )
        # Similar financial texts should be very close
        assert sim_ab > 0.8, f"Similar texts similarity too low: {sim_ab:.4f}"

    def test_query_retrieves_relevant_chunk(self, sample_chunks):
        """A query should be most similar to the semantically relevant chunk."""
        embedded = embed_chunks(sample_chunks)
        query_emb = embed_query("What is the expense ratio?")

        def cosine_sim(a, b):
            return sum(x * y for x, y in zip(a, b))

        # Find the most similar chunk
        similarities = [
            (chunk["chunk_id"], cosine_sim(query_emb, chunk["embedding"]))
            for chunk in embedded
        ]
        similarities.sort(key=lambda x: x[1], reverse=True)

        # The FAQ about expense ratio should rank highest
        top_chunk_id = similarities[0][0]
        assert "faq" in top_chunk_id or "structured_facts" in top_chunk_id, (
            f"Expected FAQ or structured_facts chunk, got {top_chunk_id}"
        )


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_chunk_with_empty_text(self):
        """Should handle a chunk with empty text without crashing."""
        chunks = [{"text": "", "chunk_id": "empty"}]
        result = embed_chunks(chunks)
        assert len(result) == 1
        assert "embedding" in result[0]
        assert len(result[0]["embedding"]) == EMBEDDING_DIM

    def test_chunk_with_very_long_text(self):
        """Should handle text longer than the model's context window."""
        long_text = "expense ratio " * 500  # Way beyond 512 tokens
        chunks = [{"text": long_text, "chunk_id": "long"}]
        result = embed_chunks(chunks)
        assert len(result) == 1
        assert len(result[0]["embedding"]) == EMBEDDING_DIM

    def test_embedding_dim_constant_matches_model(self):
        """EMBEDDING_DIM constant should match the actual model output."""
        emb = embed_query("test")
        assert len(emb) == EMBEDDING_DIM == 384
