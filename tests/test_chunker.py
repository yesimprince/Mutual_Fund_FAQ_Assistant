"""
Unit tests for the chunker module.

Tests cover:
- Structured-facts chunk contains all key FAQ fields
- FAQ chunks preserve complete Q&A pairs (never split)
- "Additional Information" boilerplate is NOT present in any chunk
- Metadata is preserved on every chunk
- Total chunk counts per scheme and overall
- No chunk exceeds ~500 tokens
- Section identification and filtering
"""

import os
import sys
import json
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.chunker import (
    build_structured_facts_chunk,
    build_faq_chunks,
    build_section_chunks,
    chunk_document,
    chunk_all,
    _estimate_tokens,
    _identify_section,
    PROCESSED_DATA_DIR,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_parsed_doc():
    """A minimal parsed document matching the real data structure."""
    return {
        "text": (
            "Scheme Overview\n"
            "Scheme: HDFC Large Cap Fund Direct Growth\n"
            "Fund House: HDFC Mutual Fund\n"
            "Category: Equity\n"
            "Plan Type: Direct\n"
            "Objective: The scheme seeks to provide long-term capital appreciation.\n"
            "Launch Date: 01-Jan-2013\n"
            "Fund Manager: Prashant Jain\n"
            "ISIN: INF179K01YV8\n"
            "Registrar Agent: CAMS\n"
            "\n\n---\n\n"
            "Key Facts\n"
            "Expense Ratio: 1.04%\n"
            "Exit Load: Exit load of 1% if redeemed within 1 year\n"
            "Minimum SIP Amount: ₹100\n"
            "NAV: ₹1227.566 (as of 09-Jul-2026)\n"
            "\n\n---\n\n"
            "Frequently Asked Questions\n"
            "Q: What is the expense ratio?\nA: The expense ratio is 1.04%.\n"
            "\n\n---\n\n"
            "Additional Information\n"
            "Groww Arbitrage Fund\nGroww ELSS Tax Saver Fund\n"
            "NIFTY 50 Options\nIPO GMP\nSME IPOs\n"
            "Top Gainers Stocks\n52 Weeks High Stocks\n"
        ),
        "metadata": {
            "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "scheme_name": "HDFC Large Cap Fund",
            "category": "Equity",
            "last_scraped_date": "2026-07-10",
        },
        "structured_fields": {
            "scheme_name": "HDFC Large Cap Fund Direct Growth",
            "fund_name": "HDFC Large Cap Fund",
            "fund_house": "HDFC Mutual Fund",
            "category": "Equity",
            "plan_type": "Direct",
            "scheme_type": "Growth",
            "description": "The scheme seeks to provide long-term capital appreciation.",
            "isin": "INF179K01YV8",
            "expense_ratio": "1.04",
            "exit_load": "Exit load of 1% if redeemed within 1 year",
            "min_sip_investment": 100,
            "min_investment_amount": 100,
            "riskometer": "Moderately High Riskometer",
            "benchmark": "NIFTY 100 Total Return Index",
            "lock_in": "No lock-in period",
            "nav": 1227.566,
            "nav_date": "09-Jul-2026",
            "aum": 39023.6868,
            "fund_manager": "Prashant Jain",
            "launch_date": "01-Jan-2013",
            "groww_rating": 4,
            "lumpsum_allowed": True,
            "max_sip_investment": 999999999,
            "min_withdrawal": 100,
            "registrar_agent": "CAMS",
        },
        "faqs": [
            {
                "question": "How to Invest in HDFC Large Cap Fund Direct Growth?",
                "answer": "You can easily invest in HDFC Large Cap Fund Direct Growth on Groww.",
            },
            {
                "question": "What kind of returns does HDFC Large Cap Fund Direct Growth provide?",
                "answer": "The average annual returns provided by this fund is 13.22% since inception.",
            },
            {
                "question": "How much expense ratio is charged by HDFC Large Cap Fund Direct Growth?",
                "answer": "The Expense Ratio of HDFC Large Cap Fund Direct Growth is 1.04% as of 10 Jul 2026.",
            },
            {
                "question": "What is the AUM of HDFC Large Cap Fund Direct Growth?",
                "answer": "The AUM is ₹39,023.69Cr as of 10 Jul 2026.",
            },
            {
                "question": "How to Redeem HDFC Large Cap Fund Direct Growth?",
                "answer": "Go to your holding on the app or web and click on redeem.",
            },
            {
                "question": "Can I invest in SIP and Lump Sum of HDFC Large Cap Fund Direct Growth?",
                "answer": "You can select either SIP or Lumpsum investment.",
            },
            {
                "question": "What is the NAV of HDFC Large Cap Fund Direct Growth?",
                "answer": "The NAV is ₹1,227.57 as of 09 Jul 2026.",
            },
            {
                "question": "What is the PE and PB ratio of HDFC Large Cap Fund Direct Growth?",
                "answer": "The PE ratio is determined by dividing market price by earnings per share.",
            },
        ],
    }


@pytest.fixture
def real_parsed_docs():
    """Load all real parsed JSON files if they exist."""
    processed_dir = os.path.normpath(PROCESSED_DATA_DIR)
    if not os.path.exists(processed_dir):
        pytest.skip("Processed data directory not found")

    docs = []
    for filename in sorted(os.listdir(processed_dir)):
        if filename.endswith(".json"):
            filepath = os.path.join(processed_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                docs.append((filename, json.load(f)))

    if not docs:
        pytest.skip("No processed JSON files found")

    return docs


# ---------------------------------------------------------------------------
# Tests: build_structured_facts_chunk
# ---------------------------------------------------------------------------

class TestStructuredFactsChunk:
    """Tests for the structured-facts chunk builder."""

    def test_contains_key_faq_fields(self, sample_parsed_doc):
        """Structured-facts chunk must contain all key FAQ fields."""
        chunk = build_structured_facts_chunk(sample_parsed_doc)
        assert chunk is not None

        text = chunk["text"]
        assert "1.04%" in text, "Missing expense_ratio"
        assert "Exit load" in text, "Missing exit_load"
        assert "1227.566" in text, "Missing NAV"
        assert "39023.6868" in text, "Missing AUM"
        assert "NIFTY 100 Total Return Index" in text, "Missing benchmark"
        assert "Moderately High" in text, "Missing riskometer"
        assert "100" in text, "Missing min SIP amount"
        assert "No lock-in period" in text, "Missing lock-in"

    def test_chunk_type_is_structured_facts(self, sample_parsed_doc):
        """Chunk type must be 'structured_facts'."""
        chunk = build_structured_facts_chunk(sample_parsed_doc)
        assert chunk["chunk_type"] == "structured_facts"

    def test_includes_scheme_name(self, sample_parsed_doc):
        """Chunk text should include the scheme name."""
        chunk = build_structured_facts_chunk(sample_parsed_doc)
        assert "HDFC Large Cap Fund" in chunk["text"]

    def test_returns_none_for_empty_fields(self):
        """Returns None when structured_fields is empty."""
        doc = {"structured_fields": {}, "metadata": {}}
        chunk = build_structured_facts_chunk(doc)
        assert chunk is None

    def test_within_token_limit(self, sample_parsed_doc):
        """Structured-facts chunk should be within ~500 tokens."""
        chunk = build_structured_facts_chunk(sample_parsed_doc)
        token_count = _estimate_tokens(chunk["text"])
        assert token_count <= 500, f"Chunk has {token_count} tokens, exceeds limit"


# ---------------------------------------------------------------------------
# Tests: build_faq_chunks
# ---------------------------------------------------------------------------

class TestFaqChunks:
    """Tests for the FAQ chunk builder."""

    def test_one_chunk_per_faq(self, sample_parsed_doc):
        """Should create exactly one chunk per FAQ entry."""
        chunks = build_faq_chunks(sample_parsed_doc)
        assert len(chunks) == 8

    def test_each_chunk_has_q_and_a(self, sample_parsed_doc):
        """Each FAQ chunk must contain both Q: and A: lines."""
        chunks = build_faq_chunks(sample_parsed_doc)
        for chunk in chunks:
            assert "Q: " in chunk["text"], f"Missing Q: in chunk: {chunk['text'][:50]}"
            assert "\nA: " in chunk["text"], f"Missing A: in chunk: {chunk['text'][:50]}"

    def test_chunk_type_is_faq(self, sample_parsed_doc):
        """All FAQ chunks must have chunk_type = 'faq'."""
        chunks = build_faq_chunks(sample_parsed_doc)
        for chunk in chunks:
            assert chunk["chunk_type"] == "faq"

    def test_qa_pairs_not_split(self, sample_parsed_doc):
        """Each chunk should contain a complete Q&A pair — question and answer together."""
        chunks = build_faq_chunks(sample_parsed_doc)
        for chunk in chunks:
            lines = chunk["text"].split("\n")
            q_lines = [l for l in lines if l.startswith("Q: ")]
            a_lines = [l for l in lines if l.startswith("A: ")]
            assert len(q_lines) == 1, "Each chunk should have exactly 1 question"
            assert len(a_lines) == 1, "Each chunk should have exactly 1 answer"

    def test_returns_empty_for_no_faqs(self):
        """Returns empty list when faqs array is missing or empty."""
        doc = {"faqs": [], "metadata": {}}
        chunks = build_faq_chunks(doc)
        assert chunks == []

    def test_within_token_limit(self, sample_parsed_doc):
        """All FAQ chunks should be within ~500 tokens."""
        chunks = build_faq_chunks(sample_parsed_doc)
        for chunk in chunks:
            token_count = _estimate_tokens(chunk["text"])
            assert token_count <= 500, f"FAQ chunk has {token_count} tokens"


# ---------------------------------------------------------------------------
# Tests: build_section_chunks
# ---------------------------------------------------------------------------

class TestSectionChunks:
    """Tests for the section-based chunk builder."""

    def test_keeps_overview_and_key_facts(self, sample_parsed_doc):
        """Should keep Scheme Overview and Key Facts sections."""
        chunks = build_section_chunks(sample_parsed_doc)
        section_headings = {c["section_heading"] for c in chunks}
        assert "Scheme Overview" in section_headings
        assert "Key Facts" in section_headings

    def test_discards_additional_information(self, sample_parsed_doc):
        """Must NOT include any text from the Additional Information section."""
        chunks = build_section_chunks(sample_parsed_doc)
        all_text = " ".join(c["text"] for c in chunks)

        # These strings are only in the "Additional Information" section
        assert "Groww Arbitrage Fund" not in all_text
        assert "NIFTY 50 Options" not in all_text
        assert "IPO GMP" not in all_text
        assert "SME IPOs" not in all_text
        assert "Top Gainers Stocks" not in all_text

    def test_discards_faq_section(self, sample_parsed_doc):
        """Must NOT create section chunks for FAQs (handled by faq chunks)."""
        chunks = build_section_chunks(sample_parsed_doc)
        section_headings = {c["section_heading"] for c in chunks}
        assert "Frequently Asked Questions" not in section_headings

    def test_chunk_type_is_section(self, sample_parsed_doc):
        """All section chunks must have chunk_type = 'section'."""
        chunks = build_section_chunks(sample_parsed_doc)
        for chunk in chunks:
            assert chunk["chunk_type"] == "section"

    def test_within_token_limit(self, sample_parsed_doc):
        """All section chunks should be within ~500 tokens."""
        chunks = build_section_chunks(sample_parsed_doc)
        for chunk in chunks:
            token_count = _estimate_tokens(chunk["text"])
            assert token_count <= 500, f"Section chunk has {token_count} tokens"


# ---------------------------------------------------------------------------
# Tests: _identify_section
# ---------------------------------------------------------------------------

class TestIdentifySection:
    """Tests for section identification logic."""

    def test_identifies_scheme_overview(self):
        assert _identify_section("Scheme Overview\nSome text") == "Scheme Overview"

    def test_identifies_key_facts(self):
        assert _identify_section("Key Facts\nSome text") == "Key Facts"

    def test_rejects_additional_information(self):
        assert _identify_section("Additional Information\nSome text") is None

    def test_rejects_faq_section(self):
        assert _identify_section("Frequently Asked Questions\nSome text") is None

    def test_rejects_unknown_section(self):
        assert _identify_section("Random Heading\nSome text") is None

    def test_handles_empty_text(self):
        assert _identify_section("") is None


# ---------------------------------------------------------------------------
# Tests: chunk_document (integration)
# ---------------------------------------------------------------------------

class TestChunkDocument:
    """Integration tests for the full document chunking pipeline."""

    def test_total_chunk_count_per_scheme(self, sample_parsed_doc):
        """Each scheme should produce ~11 chunks (1 structured + 8 FAQs + 2 sections)."""
        chunks = chunk_document(sample_parsed_doc)
        assert len(chunks) == 11, f"Expected ~11 chunks, got {len(chunks)}"

    def test_all_chunks_have_metadata(self, sample_parsed_doc):
        """Every chunk must have source_url, scheme_name, category."""
        chunks = chunk_document(sample_parsed_doc)
        for chunk in chunks:
            assert chunk.get("source_url"), f"Missing source_url in chunk {chunk.get('chunk_id')}"
            assert chunk.get("scheme_name"), f"Missing scheme_name in chunk {chunk.get('chunk_id')}"
            assert chunk.get("category"), f"Missing category in chunk {chunk.get('chunk_id')}"
            assert chunk.get("chunk_type"), f"Missing chunk_type in chunk {chunk.get('chunk_id')}"

    def test_all_chunks_have_unique_ids(self, sample_parsed_doc):
        """Every chunk must have a unique chunk_id."""
        chunks = chunk_document(sample_parsed_doc)
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids)), f"Duplicate chunk_ids found: {ids}"

    def test_chunk_id_format(self, sample_parsed_doc):
        """Chunk IDs should follow the {slug}_{type}_{index} pattern."""
        chunks = chunk_document(sample_parsed_doc)
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            parts = chunk_id.rsplit("_", 2)
            assert len(parts) >= 3, f"Invalid chunk_id format: {chunk_id}"

    def test_four_chunk_types_present(self, sample_parsed_doc):
        """All 4 chunk types should be present: structured_facts, faq, section."""
        chunks = chunk_document(sample_parsed_doc)
        types = {c["chunk_type"] for c in chunks}
        assert "structured_facts" in types
        assert "faq" in types
        assert "section" in types

    def test_no_boilerplate_in_any_chunk(self, sample_parsed_doc):
        """No chunk should contain Groww site boilerplate content."""
        chunks = chunk_document(sample_parsed_doc)
        boilerplate_markers = [
            "Groww Arbitrage Fund",
            "NIFTY 50 Options",
            "IPO GMP",
            "SME IPOs",
            "Top Gainers Stocks",
            "52 Weeks High Stocks",
        ]
        for chunk in chunks:
            for marker in boilerplate_markers:
                assert marker not in chunk["text"], (
                    f"Boilerplate '{marker}' found in chunk {chunk['chunk_id']}"
                )

    def test_no_chunk_exceeds_token_limit(self, sample_parsed_doc):
        """No chunk should exceed ~500 tokens."""
        chunks = chunk_document(sample_parsed_doc)
        for chunk in chunks:
            token_count = _estimate_tokens(chunk["text"])
            assert token_count <= 500, (
                f"Chunk {chunk['chunk_id']} has {token_count} tokens"
            )

    def test_last_scraped_date_propagated(self, sample_parsed_doc):
        """last_scraped_date from metadata should be on every chunk."""
        chunks = chunk_document(sample_parsed_doc)
        for chunk in chunks:
            assert chunk.get("last_scraped_date") == "2026-07-10"


# ---------------------------------------------------------------------------
# Tests: Real data integration (requires data/processed/ files)
# ---------------------------------------------------------------------------

class TestRealData:
    """Integration tests using actual parsed JSON files."""

    def test_total_chunks_across_all_schemes(self, real_parsed_docs):
        """Total chunks across all 5 schemes should be ~55."""
        total = 0
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            total += len(chunks)

        assert 40 <= total <= 80, (
            f"Expected ~55 total chunks, got {total}"
        )

    def test_chunks_per_scheme_is_reasonable(self, real_parsed_docs):
        """Each scheme should produce roughly 11 chunks."""
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            assert 8 <= len(chunks) <= 20, (
                f"{filename}: expected ~11 chunks, got {len(chunks)}"
            )

    def test_no_boilerplate_in_real_data(self, real_parsed_docs):
        """Real data chunks should not contain Groww boilerplate."""
        boilerplate_markers = [
            "Groww Arbitrage Fund",
            "NIFTY 50 Options",
            "IPO GMP",
            "Top Gainers Stocks",
            "52 Weeks High Stocks",
            "Bajaj Finance Options",
            "Tata Motors Futures",
            "SIP Calculator",
            "Brokerage Calculator",
            "Terms and Conditions",
            "Privacy Policy",
            "Bug Bounty",
        ]
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            for chunk in chunks:
                for marker in boilerplate_markers:
                    assert marker not in chunk["text"], (
                        f"Boilerplate '{marker}' found in {filename}, "
                        f"chunk {chunk['chunk_id']}"
                    )

    def test_real_structured_facts_contain_key_fields(self, real_parsed_docs):
        """Real structured-facts chunks must have expense ratio, NAV, etc."""
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            sf_chunks = [c for c in chunks if c["chunk_type"] == "structured_facts"]
            assert len(sf_chunks) == 1, f"{filename}: expected 1 structured_facts chunk"

            text = sf_chunks[0]["text"]
            assert "Expense Ratio" in text, f"{filename}: missing Expense Ratio"
            assert "NAV" in text, f"{filename}: missing NAV"

    def test_real_faq_chunks_have_qa_pairs(self, real_parsed_docs):
        """Real FAQ chunks must have Q: and A: lines."""
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            faq_chunks = [c for c in chunks if c["chunk_type"] == "faq"]
            assert len(faq_chunks) >= 1, f"{filename}: no FAQ chunks found"

            for chunk in faq_chunks:
                assert "Q: " in chunk["text"], f"{filename}: FAQ missing Q:"
                assert "\nA: " in chunk["text"], f"{filename}: FAQ missing A:"

    def test_no_real_chunk_exceeds_token_limit(self, real_parsed_docs):
        """No real data chunk should exceed ~500 tokens."""
        for filename, doc in real_parsed_docs:
            chunks = chunk_document(doc)
            for chunk in chunks:
                token_count = _estimate_tokens(chunk["text"])
                assert token_count <= 500, (
                    f"{filename}, chunk {chunk['chunk_id']}: "
                    f"{token_count} tokens exceeds limit"
                )


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_document(self):
        """Should handle an empty document gracefully."""
        doc = {"text": "", "metadata": {}, "structured_fields": {}, "faqs": []}
        chunks = chunk_document(doc)
        assert chunks == []

    def test_missing_fields(self):
        """Should handle a document with missing keys."""
        doc = {"metadata": {"source_url": "https://example.com", "scheme_name": "Test"}}
        chunks = chunk_document(doc)
        # Should not crash, may produce 0 chunks
        assert isinstance(chunks, list)

    def test_token_estimation(self):
        """Token estimation should be roughly correct."""
        text = "This is a simple test sentence with ten words total here"
        tokens = _estimate_tokens(text)
        assert 8 <= tokens <= 15
