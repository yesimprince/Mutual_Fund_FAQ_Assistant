"""
Tests for the retrieval pipeline (Phase 7).

Tests cover:
- L2-to-cosine similarity conversion
- search() returning results for factual queries
- Results containing required metadata fields
- SIMILARITY_THRESHOLD filtering (irrelevant queries → empty)
- scheme_name filter narrowing results
- Reranker passthrough returning top-k sorted by similarity
- Reranker toggle (RERANKER_ENABLED = False) skipping reranking
"""

import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.retriever import (
    search,
    _l2_to_cosine_similarity,
    SIMILARITY_THRESHOLD,
    DEFAULT_TOP_K,
    RERANKER_ENABLED,
    RERANKER_TOP_K,
)
from src.retrieval.reranker import rerank
from src.ingestion.vectorstore import init_vectorstore


# ============================================================================
# Test: L2-to-Cosine Conversion
# ============================================================================

class TestL2ToCosineConversion:
    """Test the distance conversion formula: cosine_sim = 1 - (L2_dist / 2)."""

    def test_zero_distance_is_perfect_similarity(self):
        """L2 distance of 0 → cosine similarity of 1.0 (identical vectors)."""
        assert _l2_to_cosine_similarity(0.0) == 1.0

    def test_max_distance_is_negative_similarity(self):
        """L2 distance of 2.0 → cosine similarity of 0.0 (orthogonal vectors for normalized)."""
        assert _l2_to_cosine_similarity(2.0) == 0.0

    def test_known_distance_values(self):
        """Verify conversion against known empirical values from Phase 7.2 analysis."""
        # "expense ratio HDFC Large Cap" → L2=0.2328, expected sim≈0.8836
        sim = _l2_to_cosine_similarity(0.2328)
        assert abs(sim - 0.8836) < 0.0001

        # "exit load HDFC Small Cap" → L2=0.5233, expected sim≈0.7384
        sim = _l2_to_cosine_similarity(0.5233)
        assert abs(sim - 0.73835) < 0.001

        # "weather" (irrelevant) → L2=1.2006, expected sim≈0.3997
        sim = _l2_to_cosine_similarity(1.2006)
        assert abs(sim - 0.3997) < 0.0001

    def test_negative_distance_gives_above_one(self):
        """Edge case: negative L2 distance → similarity > 1.0."""
        sim = _l2_to_cosine_similarity(-0.1)
        assert sim > 1.0

    def test_large_distance_gives_negative_similarity(self):
        """Very large L2 distance → negative cosine similarity."""
        sim = _l2_to_cosine_similarity(3.0)
        assert sim < 0.0


# ============================================================================
# Test: Config Defaults
# ============================================================================

class TestConfigDefaults:
    """Verify configuration constants match the plan."""

    def test_similarity_threshold(self):
        """SIMILARITY_THRESHOLD should be 0.55 (calibrated from empirical testing)."""
        assert SIMILARITY_THRESHOLD == 0.55

    def test_default_top_k(self):
        """DEFAULT_TOP_K should be 5."""
        assert DEFAULT_TOP_K == 5

    def test_reranker_disabled_by_default(self):
        """RERANKER_ENABLED should be False by default."""
        assert RERANKER_ENABLED is False

    def test_reranker_top_k(self):
        """RERANKER_TOP_K should be 3."""
        assert RERANKER_TOP_K == 3


# ============================================================================
# Test: Reranker (Passthrough Mode)
# ============================================================================

class TestReranker:
    """Test the passthrough reranker."""

    def test_rerank_empty_list(self):
        """Reranking an empty list returns an empty list."""
        result = rerank(query="test", chunks=[], top_k=3)
        assert result == []

    def test_rerank_returns_top_k(self):
        """Passthrough reranker returns exactly top_k chunks."""
        chunks = [
            {"text": f"chunk {i}", "similarity": 0.9 - (i * 0.1)}
            for i in range(5)
        ]
        result = rerank(query="test", chunks=chunks, top_k=3)
        assert len(result) == 3

    def test_rerank_sorted_by_similarity(self):
        """Passthrough reranker sorts by descending similarity."""
        chunks = [
            {"text": "low", "similarity": 0.5},
            {"text": "high", "similarity": 0.9},
            {"text": "mid", "similarity": 0.7},
        ]
        result = rerank(query="test", chunks=chunks, top_k=3)
        assert result[0]["text"] == "high"
        assert result[1]["text"] == "mid"
        assert result[2]["text"] == "low"

    def test_rerank_fewer_than_top_k(self):
        """If fewer chunks than top_k, return all of them."""
        chunks = [
            {"text": "only one", "similarity": 0.8},
        ]
        result = rerank(query="test", chunks=chunks, top_k=3)
        assert len(result) == 1

    def test_rerank_preserves_metadata(self):
        """Reranker preserves all chunk fields, not just text and similarity."""
        chunks = [
            {
                "text": "test chunk",
                "similarity": 0.8,
                "chunk_id": "test_faq_0",
                "scheme_name": "HDFC Large Cap Fund",
                "source_url": "https://groww.in/test",
                "chunk_type": "faq",
            },
        ]
        result = rerank(query="test", chunks=chunks, top_k=3)
        assert result[0]["chunk_id"] == "test_faq_0"
        assert result[0]["scheme_name"] == "HDFC Large Cap Fund"
        assert result[0]["chunk_type"] == "faq"


# ============================================================================
# Test: search() — Integration Tests (require populated vector store)
# ============================================================================

class TestSearchIntegration:
    """
    Integration tests for the search() function.

    These tests require a populated ChromaDB vector store at vectorstore/.
    They query the live index to verify end-to-end retrieval behaviour.
    """

    @classmethod
    def setup_class(cls):
        """Check vector store availability before running any tests."""
        try:
            collection = init_vectorstore()
            count = collection.count()
            if count == 0:
                pytest.skip("Vector store is empty — run ingest.py first")
        except Exception as e:
            pytest.skip(f"Could not connect to ChromaDB vector store: {e}")

    def test_relevant_query_returns_results(self):
        """A relevant factual query should return at least 1 result."""
        results = search("What is the expense ratio of HDFC Large Cap Fund?")
        assert len(results) > 0

    def test_results_have_required_fields(self):
        """Each result must have the required metadata fields."""
        results = search("What is the expense ratio of HDFC Large Cap Fund?")
        assert len(results) > 0

        required_fields = [
            "chunk_id", "text", "similarity",
            "scheme_name", "source_url", "chunk_type",
        ]
        for result in results:
            for field in required_fields:
                assert field in result, f"Missing field: {field}"

    def test_similarity_scores_are_valid(self):
        """Similarity scores should be >= SIMILARITY_THRESHOLD and <= 1.0."""
        results = search("expense ratio HDFC Large Cap")
        for result in results:
            assert result["similarity"] >= SIMILARITY_THRESHOLD, (
                f"Similarity {result['similarity']} is below threshold {SIMILARITY_THRESHOLD}"
            )
            assert result["similarity"] <= 1.0, (
                f"Similarity {result['similarity']} exceeds 1.0"
            )

    def test_results_sorted_by_similarity_descending(self):
        """Results should be sorted by similarity in descending order."""
        results = search("expense ratio")
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i]["similarity"] >= results[i + 1]["similarity"]

    def test_max_results_capped_at_reranker_top_k(self):
        """Results count should not exceed RERANKER_TOP_K (3)."""
        results = search("expense ratio")
        assert len(results) <= RERANKER_TOP_K

    def test_irrelevant_query_returns_empty(self):
        """An off-topic query should return no results (filtered by threshold)."""
        results = search("What is the weather today?")
        assert len(results) == 0, (
            f"Expected empty results for irrelevant query, got {len(results)} results"
        )

    def test_scheme_name_filter(self):
        """Filtering by scheme_name should only return chunks from that scheme."""
        results = search(
            "expense ratio",
            scheme_name="HDFC Large Cap Fund",
        )
        for result in results:
            assert result["scheme_name"] == "HDFC Large Cap Fund", (
                f"Expected scheme 'HDFC Large Cap Fund', got '{result['scheme_name']}'"
            )

    def test_scheme_name_filter_excludes_others(self):
        """scheme_name filter should exclude chunks from other schemes."""
        results = search(
            "expense ratio",
            scheme_name="HDFC Small Cap Fund",
        )
        for result in results:
            assert "Large Cap" not in result["scheme_name"]
            assert "Mid Cap" not in result["scheme_name"]

    def test_expense_ratio_query_returns_correct_chunk_type(self):
        """Expense ratio query should return faq or structured_facts chunks."""
        results = search("What is the expense ratio of HDFC Large Cap Fund?")
        assert len(results) > 0
        top_result = results[0]
        assert top_result["chunk_type"] in ("faq", "structured_facts"), (
            f"Expected faq or structured_facts, got '{top_result['chunk_type']}'"
        )

    def test_expense_ratio_query_returns_correct_scheme(self):
        """Expense ratio query for HDFC Large Cap should return chunks from that scheme."""
        results = search("What is the expense ratio of HDFC Large Cap Fund?")
        assert len(results) > 0
        top_result = results[0]
        assert "Large Cap" in top_result["scheme_name"], (
            f"Top result scheme '{top_result['scheme_name']}' doesn't match query scheme"
        )

    def test_empty_query_returns_empty(self):
        """An empty query string should return no results."""
        results = search("")
        assert results == []

    def test_whitespace_query_returns_empty(self):
        """A whitespace-only query should return no results."""
        results = search("   ")
        assert results == []

    def test_exit_load_query(self):
        """Exit load query should return relevant results."""
        results = search("exit load HDFC Small Cap")
        # Should return results (even if borderline)
        # The structured_facts chunk should mention exit load
        if results:
            assert any("Small Cap" in r.get("scheme_name", "") for r in results)

    def test_distance_field_removed_from_output(self):
        """The raw 'distance' field from ChromaDB should be cleaned up."""
        results = search("expense ratio")
        for result in results:
            assert "distance" not in result, (
                "Raw 'distance' field should be removed; use 'similarity' instead"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
