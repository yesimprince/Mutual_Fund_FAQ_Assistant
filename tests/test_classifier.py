"""
Tests for the Query Classifier (src/pipeline/query_classifier.py).

Tests cover:
    - Factual query classification
    - Advisory query classification (keywords + regex)
    - PII detection (PAN, Aadhaar, email, phone)
    - Edge cases (empty queries, mixed signals)
"""

import pytest

from src.pipeline.query_classifier import classify, _has_pii, _is_advisory


# =========================================================================
# Factual Queries
# =========================================================================

class TestFactualQueries:
    """Factual queries should be classified as 'factual'."""

    @pytest.mark.parametrize("query", [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "What is the exit load for HDFC Small Cap Fund?",
        "What is the minimum SIP amount for HDFC Mid Cap Fund?",
        "Tell me the NAV of HDFC Gold ETF FoF",
        "What is the benchmark index for HDFC Large Cap?",
        "What is the AUM of HDFC Silver ETF FoF?",
        "What is the riskometer classification?",
        "Who is the fund manager of HDFC Large Cap Fund?",
        "What is the ISIN of HDFC Mid Cap Fund?",
        "What is the lock-in period for HDFC Large Cap?",
        "expense ratio HDFC Small Cap",
        "exit load details",
        "minimum lumpsum amount",
    ])
    def test_factual_queries(self, query):
        assert classify(query) == "factual"


# =========================================================================
# Advisory Queries
# =========================================================================

class TestAdvisoryQueries:
    """Advisory queries should be classified as 'advisory'."""

    @pytest.mark.parametrize("query", [
        "Should I invest in HDFC Mid Cap Fund?",
        "Which is better, HDFC Large Cap or HDFC Mid Cap?",
        "Can you recommend a good mutual fund?",
        "Suggest a fund for long-term investment",
        "Please advise me on which fund to choose",
        "Is HDFC Large Cap a good fund?",
        "What is the best fund for beginners?",
        "Should I invest in this fund or that one?",
        "Will HDFC Small Cap give good returns?",
        "Is it worth investing in HDFC Gold ETF?",
        "Compare HDFC Large Cap and HDFC Mid Cap",
        "Is HDFC Large Cap better option than Mid Cap?",
        "What do you think about HDFC Small Cap?",
        "Will it perform well in the future?",
        "Can I get 15% return from this fund?",
        "Is it safe to invest in HDFC Mid Cap?",
        "How much return can I expect?",
        "HDFC Large Cap vs HDFC Mid Cap",
    ])
    def test_advisory_queries(self, query):
        assert classify(query) == "advisory"


# =========================================================================
# PII Detection
# =========================================================================

class TestPIIDetection:
    """Queries containing PII should be classified as 'pii_detected'."""

    @pytest.mark.parametrize("query,description", [
        ("My PAN is ABCDE1234F", "PAN card number"),
        ("PAN card: BXYPG5678H", "PAN with prefix text"),
        ("Here is my PAN ZCDEF9012G for KYC", "PAN in middle of text"),
        ("Contact me at user@example.com", "Email address"),
        ("Send details to john.doe@gmail.com", "Email with dots"),
    ])
    def test_pii_detected_high_confidence(self, query, description):
        result = classify(query)
        assert result == "pii_detected", f"Failed for: {description}"

    @pytest.mark.parametrize("query,description", [
        ("My aadhaar number is 1234 5678 9012", "Aadhaar with spaces"),
        ("My Aadhaar is 123456789012", "Aadhaar without spaces"),
        ("My phone number is 9876543210", "Phone number"),
        ("Contact me at +91 9876543210", "Phone with country code"),
        ("my mobile number is 8765432109", "Mobile number"),
    ])
    def test_pii_detected_with_context(self, query, description):
        result = classify(query)
        assert result == "pii_detected", f"Failed for: {description}"


# =========================================================================
# Edge Cases
# =========================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_query(self):
        assert classify("") == "factual"

    def test_whitespace_only(self):
        assert classify("   ") == "factual"

    def test_pii_takes_priority_over_advisory(self):
        """PII should be detected even if query is also advisory."""
        query = "Should I invest? My PAN is ABCDE1234F"
        assert classify(query) == "pii_detected"

    def test_case_insensitive_advisory(self):
        """Advisory keywords should be case-insensitive."""
        assert classify("SHOULD I INVEST IN THIS FUND?") == "advisory"
        assert classify("Should I Invest In This Fund?") == "advisory"

    def test_non_pii_numbers_are_factual(self):
        """Numbers that aren't PII (NAV, AUM) should not trigger PII detection."""
        assert classify("What is the NAV ₹1227.566?") == "factual"
        assert classify("AUM is 39023.69 Cr") == "factual"
        assert classify("Expense ratio is 1.04%") == "factual"


# =========================================================================
# Internal Helper Tests
# =========================================================================

class TestHasPII:
    """Direct tests for _has_pii helper."""

    def test_pan_detection(self):
        assert _has_pii("ABCDE1234F") is True

    def test_email_detection(self):
        assert _has_pii("user@example.com") is True

    def test_clean_text(self):
        assert _has_pii("What is the expense ratio?") is False


class TestIsAdvisory:
    """Direct tests for _is_advisory helper."""

    def test_keyword_match(self):
        assert _is_advisory("Should I invest in HDFC?") is True

    def test_pattern_match(self):
        assert _is_advisory("Is HDFC a good fund to buy?") is True

    def test_factual_not_advisory(self):
        assert _is_advisory("What is the expense ratio?") is False
