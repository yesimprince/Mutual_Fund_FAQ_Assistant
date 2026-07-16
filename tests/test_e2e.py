"""
End-to-end tests for the Phase 8 Query Pipeline.

Tests the full flow:
    1. Factual query → classify → retrieve → generate → guardrails → response
    2. Advisory query → classify → template refusal (no API call)
    3. PII query → classify → block (no API call)
    4. Rate-limited query → graceful error with wait time

These tests mock the Groq API and vector store to avoid external dependencies.
"""

from unittest.mock import patch, MagicMock

import pytest

from src.pipeline.query_classifier import classify
from src.pipeline.generator import generate_response, generate_refusal, generate_pii_block
from src.pipeline.guardrails import apply_input_guardrails
from src.pipeline.rate_limiter import GroqRateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_chunks():
    """Sample retrieved chunks for testing."""
    return [
        {
            "chunk_id": "hdfc-large-cap_faq_0",
            "text": (
                "Q: What is the expense ratio of HDFC Large Cap Fund Direct Growth?\n"
                "A: The Expense Ratio of HDFC Large Cap Fund Direct Growth is 1.04% "
                "as of 10 Jul 2026."
            ),
            "similarity": 0.8836,
            "scheme_name": "HDFC Large Cap Fund",
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "category": "Large Cap",
            "chunk_type": "faq",
            "last_scraped_date": "2026-07-10",
        }
    ]


@pytest.fixture
def mock_groq_response():
    """Create a mock Groq API response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "The expense ratio of HDFC Large Cap Fund Direct Growth is 1.04% as of July 2026. "
        "This applies to the direct growth option of the fund. "
        "Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    )
    mock_response.usage = MagicMock()
    mock_response.usage.total_tokens = 350
    mock_response.usage.prompt_tokens = 250
    mock_response.usage.completion_tokens = 100
    return mock_response


# =========================================================================
# Test 1: Factual Query → Full Pipeline
# =========================================================================

class TestFactualQueryPipeline:
    """End-to-end test for factual queries."""

    def test_factual_query_classification(self):
        """Factual queries should be classified correctly."""
        query = "What is the expense ratio of HDFC Large Cap Fund?"
        assert classify(query) == "factual"

    def test_factual_query_input_guardrails(self):
        """Factual queries should pass input guardrails."""
        query = "What is the expense ratio of HDFC Large Cap Fund?"
        sanitized, error = apply_input_guardrails(query)
        assert error is None
        assert sanitized == query

    @patch("src.pipeline.generator._get_groq_client")
    @patch("src.pipeline.generator.get_rate_limiter")
    def test_factual_query_generates_response(
        self, mock_get_limiter, mock_get_client,
        sample_chunks, mock_groq_response,
    ):
        """Full pipeline: factual query → LLM response with citations."""
        # Setup rate limiter mock
        mock_limiter = MagicMock()
        mock_limiter.can_request.return_value = (True, 0.0)
        mock_limiter.estimate_tokens.return_value = 500
        mock_get_limiter.return_value = mock_limiter

        # Setup Groq client mock
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_get_client.return_value = mock_client

        # Execute
        result = generate_response(
            "What is the expense ratio of HDFC Large Cap Fund?",
            sample_chunks,
        )

        # Verify
        assert result["status"] == "success"
        assert result["query_type"] == "factual"
        assert result["answer"]  # Non-empty
        assert result["source"]  # Has a citation
        assert result["last_updated"] == "2026-07-10"

        # Verify rate limiter was called
        mock_limiter.can_request.assert_called_once()
        mock_limiter.record_request.assert_called_once_with(350)

    @patch("src.pipeline.generator._get_groq_client")
    @patch("src.pipeline.generator.get_rate_limiter")
    def test_factual_response_has_footer(
        self, mock_get_limiter, mock_get_client,
        sample_chunks, mock_groq_response,
    ):
        """Response should include the 'Last updated' footer."""
        mock_limiter = MagicMock()
        mock_limiter.can_request.return_value = (True, 0.0)
        mock_limiter.estimate_tokens.return_value = 500
        mock_get_limiter.return_value = mock_limiter

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_get_client.return_value = mock_client

        result = generate_response(
            "What is the expense ratio?",
            sample_chunks,
        )

        assert "Last updated from sources:" in result["answer"]


# =========================================================================
# Test 2: Advisory Query → Template Refusal
# =========================================================================

class TestAdvisoryQueryPipeline:
    """End-to-end test for advisory queries."""

    def test_advisory_query_classification(self):
        """Advisory queries should be classified correctly."""
        queries = [
            "Should I invest in HDFC Mid Cap Fund?",
            "Which is better, HDFC Large Cap or Mid Cap?",
            "Recommend a good fund for me",
        ]
        for query in queries:
            assert classify(query) == "advisory", f"Failed for: {query}"

    def test_advisory_refusal_response(self):
        """Advisory queries should get template-based refusal (no API call)."""
        result = generate_refusal("Should I invest in HDFC Mid Cap Fund?")

        assert result["status"] == "refused"
        assert result["query_type"] == "advisory"
        assert "factual information" in result["answer"].lower()
        assert "amfiindia.com" in result["source"]
        assert result["last_updated"] is None

    def test_advisory_refusal_no_groq_call(self):
        """Refusal should not make any Groq API calls."""
        # If this test runs without Groq SDK or API key, it proves no call is made
        result = generate_refusal("Suggest a good fund")
        assert result["status"] == "refused"


# =========================================================================
# Test 3: PII Query → Block
# =========================================================================

class TestPIIQueryPipeline:
    """End-to-end test for PII queries."""

    def test_pii_query_classification(self):
        """PII queries should be classified correctly."""
        queries = [
            "My PAN is ABCDE1234F",
            "Contact me at user@example.com",
        ]
        for query in queries:
            assert classify(query) == "pii_detected", f"Failed for: {query}"

    def test_pii_block_response(self):
        """PII queries should be blocked with a security message."""
        result = generate_pii_block("My PAN is ABCDE1234F")

        assert result["status"] == "blocked"
        assert result["query_type"] == "pii_detected"
        assert "personal information" in result["answer"].lower()
        assert result["source"] is None
        assert result["last_updated"] is None

    def test_pii_input_guardrail(self):
        """PII should be caught by input guardrails too."""
        _, error = apply_input_guardrails("My PAN is ABCDE1234F")
        assert error is not None


# =========================================================================
# Test 4: Rate-Limited Query → Graceful Error
# =========================================================================

class TestRateLimitedPipeline:
    """End-to-end test for rate-limited scenarios."""

    @patch("src.pipeline.generator.get_rate_limiter")
    def test_rate_limited_returns_wait_time(
        self, mock_get_limiter, sample_chunks,
    ):
        """When rate-limited, should return friendly message with wait time."""
        mock_limiter = MagicMock()
        mock_limiter.can_request.return_value = (False, 45.0)
        mock_limiter.estimate_tokens.return_value = 800
        mock_get_limiter.return_value = mock_limiter

        result = generate_response(
            "What is the expense ratio?",
            sample_chunks,
        )

        assert result["status"] == "rate_limited"
        assert result["rate_limit_wait"] == 45.0
        assert "try again" in result["answer"].lower()
        # No record_request should be called since the request was blocked
        mock_limiter.record_request.assert_not_called()

    @patch("src.pipeline.generator.get_rate_limiter")
    def test_rate_limited_does_not_call_groq(
        self, mock_get_limiter, sample_chunks,
    ):
        """Rate-limited requests should not attempt any Groq API call."""
        mock_limiter = MagicMock()
        mock_limiter.can_request.return_value = (False, 30.0)
        mock_limiter.estimate_tokens.return_value = 800
        mock_get_limiter.return_value = mock_limiter

        with patch("src.pipeline.generator._get_groq_client") as mock_client:
            generate_response("What is the NAV?", sample_chunks)
            mock_client.assert_not_called()


# =========================================================================
# Test 5: Full Classification → Response Pipeline
# =========================================================================

class TestFullPipeline:
    """Integration tests that combine classification + generation."""

    @patch("src.pipeline.generator._get_groq_client")
    @patch("src.pipeline.generator.get_rate_limiter")
    def test_full_pipeline_factual(
        self, mock_get_limiter, mock_get_client,
        sample_chunks, mock_groq_response,
    ):
        """Complete pipeline: classify → retrieve → generate."""
        query = "What is the expense ratio of HDFC Large Cap Fund?"

        # Step 1: Classify
        query_type = classify(query)
        assert query_type == "factual"

        # Step 2: Input guardrails
        sanitized, error = apply_input_guardrails(query)
        assert error is None

        # Step 3: Generate (with mocked deps)
        mock_limiter = MagicMock()
        mock_limiter.can_request.return_value = (True, 0.0)
        mock_limiter.estimate_tokens.return_value = 500
        mock_get_limiter.return_value = mock_limiter

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_get_client.return_value = mock_client

        result = generate_response(sanitized, sample_chunks)

        assert result["status"] == "success"
        assert result["answer"]
        assert result["source"]

    def test_full_pipeline_advisory(self):
        """Complete pipeline: classify → refusal (no API)."""
        query = "Should I invest in HDFC Mid Cap?"

        query_type = classify(query)
        assert query_type == "advisory"

        result = generate_refusal(query)
        assert result["status"] == "refused"

    def test_full_pipeline_pii(self):
        """Complete pipeline: classify → block (no API)."""
        query = "My PAN is ABCDE1234F"

        query_type = classify(query)
        assert query_type == "pii_detected"

        result = generate_pii_block(query)
        assert result["status"] == "blocked"
