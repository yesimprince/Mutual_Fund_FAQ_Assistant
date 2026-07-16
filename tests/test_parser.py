"""
Unit tests for the parser module.

Tests:
- __NEXT_DATA__ extraction
- Structured field extraction
- FAQ schema.org extraction
- Clean text generation
- Metadata mapping
- parse_all integration
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.parser import (
    parse_html,
    parse_all,
    extract_metadata,
    SCHEME_MAP,
    _extract_next_data,
    _extract_structured_fields,
    _extract_faq_schema,
    _format_lock_in,
    _clean_html_text,
)
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Sample data for testing
# ---------------------------------------------------------------------------
SAMPLE_NEXT_DATA = json.dumps({
    "props": {
        "pageProps": {
            "mfServerSideData": {
                "scheme_name": "HDFC Large Cap Fund Direct Growth",
                "fund_name": "HDFC Large Cap Fund",
                "fund_house": "HDFC Mutual Fund",
                "category": "Equity",
                "plan_type": "Direct",
                "scheme_type": "Growth",
                "description": "Long-term capital appreciation.",
                "isin": "INF179K01YV8",
                "expense_ratio": 1.04,
                "exit_load": "Exit load of 1% if redeemed within 1 year",
                "min_sip_investment": 100,
                "min_investment_amount": 100,
                "nfo_risk": "Very High Risk",
                "benchmark_name": "NIFTY 100 Total Return Index",
                "benchmark": "NIFTY 100 TRI",
                "lock_in": {"years": None, "months": None, "days": None},
                "nav": 1227.566,
                "nav_date": "09-Jul-2026",
                "aum": 39023.69,
                "fund_manager": "Rahul Baijal",
                "launch_date": "01-Jan-2013",
                "groww_rating": 4,
                "lumpsum_allowed": True,
                "max_sip_investment": 999999999,
                "min_withdrawal": 100,
                "registrar_agent": "CAMS",
            }
        }
    }
})

SAMPLE_FAQ_SCHEMA = json.dumps({
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "What is the expense ratio of HDFC Large Cap Fund?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "<p>The expense ratio is 1.04%.</p>"
            }
        },
        {
            "@type": "Question",
            "name": "What is the exit load?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "<p>Exit load of 1% if redeemed within 1 year.</p>"
            }
        }
    ]
})

SAMPLE_HTML = f"""
<html>
<head>
    <title>HDFC Large Cap Fund Direct Growth</title>
    <script id="__NEXT_DATA__" type="application/json">{SAMPLE_NEXT_DATA}</script>
    <script type="application/ld+json">{SAMPLE_FAQ_SCHEMA}</script>
</head>
<body>
    <nav>Navigation bar content</nav>
    <div>HDFC Large Cap Fund Direct Growth is a Equity Mutual Fund Scheme launched by HDFC Mutual Fund.</div>
    <div>Expense ratio: 1.04%</div>
    <div>Min. for SIP: ₹100</div>
    <footer>Footer content</footer>
    <script>console.log("should be removed")</script>
</body>
</html>
"""


class TestExtractNextData(unittest.TestCase):
    """Test __NEXT_DATA__ extraction."""

    def test_extracts_mf_data(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        mf_data = _extract_next_data(soup)
        self.assertIsNotNone(mf_data)
        self.assertEqual(mf_data["fund_name"], "HDFC Large Cap Fund")

    def test_returns_none_when_missing(self):
        soup = BeautifulSoup("<html><body>No data</body></html>", "html.parser")
        result = _extract_next_data(soup)
        self.assertIsNone(result)

    def test_returns_none_for_invalid_json(self):
        html = '<html><script id="__NEXT_DATA__">not valid json</script></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_next_data(soup)
        self.assertIsNone(result)


class TestStructuredFields(unittest.TestCase):
    """Test structured field extraction from mfServerSideData."""

    def setUp(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        self.mf_data = _extract_next_data(soup)
        self.fields = _extract_structured_fields(self.mf_data)

    def test_expense_ratio(self):
        self.assertEqual(self.fields["expense_ratio"], 1.04)

    def test_exit_load(self):
        self.assertIn("1%", self.fields["exit_load"])

    def test_min_sip(self):
        self.assertEqual(self.fields["min_sip_investment"], 100)

    def test_riskometer(self):
        self.assertEqual(self.fields["riskometer"], "Very High Risk")

    def test_benchmark(self):
        self.assertIn("NIFTY 100", self.fields["benchmark"])

    def test_lock_in_no_period(self):
        self.assertEqual(self.fields["lock_in"], "No lock-in period")

    def test_nav(self):
        self.assertAlmostEqual(self.fields["nav"], 1227.566)

    def test_fund_manager(self):
        self.assertEqual(self.fields["fund_manager"], "Rahul Baijal")


class TestFormatLockIn(unittest.TestCase):
    """Test lock-in period formatting."""

    def test_no_lock_in(self):
        self.assertEqual(_format_lock_in({}), "No lock-in period")

    def test_null_values(self):
        self.assertEqual(
            _format_lock_in({"years": None, "months": None, "days": None}),
            "No lock-in period"
        )

    def test_3_years(self):
        self.assertEqual(_format_lock_in({"years": 3}), "3 years")

    def test_1_year(self):
        self.assertEqual(_format_lock_in({"years": 1}), "1 year")

    def test_mixed(self):
        result = _format_lock_in({"years": 1, "months": 6})
        self.assertIn("1 year", result)
        self.assertIn("6 months", result)


class TestFAQSchema(unittest.TestCase):
    """Test FAQ schema.org extraction."""

    def test_extracts_faqs(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        faqs = _extract_faq_schema(soup)
        self.assertEqual(len(faqs), 2)
        self.assertIn("expense ratio", faqs[0]["question"].lower())

    def test_strips_html_from_answers(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        faqs = _extract_faq_schema(soup)
        for faq in faqs:
            self.assertNotIn("<p>", faq["answer"])
            self.assertNotIn("</p>", faq["answer"])

    def test_no_faq_schema(self):
        soup = BeautifulSoup("<html><body>No FAQ</body></html>", "html.parser")
        faqs = _extract_faq_schema(soup)
        self.assertEqual(faqs, [])


class TestCleanHTMLText(unittest.TestCase):
    """Test HTML text cleaning."""

    def test_removes_scripts(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        text = _clean_html_text(soup)
        self.assertNotIn("console.log", text)

    def test_removes_nav_footer(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        text = _clean_html_text(soup)
        self.assertNotIn("Navigation bar content", text)
        self.assertNotIn("Footer content", text)

    def test_preserves_content(self):
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        text = _clean_html_text(soup)
        self.assertIn("HDFC Large Cap Fund", text)


class TestMetadata(unittest.TestCase):
    """Test metadata extraction."""

    def test_known_slug(self):
        meta = extract_metadata(
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        self.assertEqual(meta["scheme_name"], "HDFC Large Cap Fund")
        self.assertEqual(meta["category"], "Large Cap")
        self.assertTrue(meta["source_url"].startswith("https://groww.in/"))
        self.assertRegex(meta["last_scraped_date"], r"\d{4}-\d{2}-\d{2}")

    def test_unknown_slug(self):
        meta = extract_metadata("https://groww.in/mutual-funds/unknown", "unknown")
        self.assertEqual(meta["scheme_name"], "Unknown")
        self.assertEqual(meta["category"], "Unknown")

    def test_all_schemes_mapped(self):
        self.assertEqual(len(SCHEME_MAP), 5)
        for slug, (name, cat) in SCHEME_MAP.items():
            self.assertGreater(len(name), 0)
            self.assertGreater(len(cat), 0)


class TestParseHTML(unittest.TestCase):
    """Test the main parse_html function."""

    def test_produces_non_empty_text(self):
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        self.assertGreater(len(result["text"]), 50)

    def test_has_metadata(self):
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        meta = result["metadata"]
        self.assertIn("source_url", meta)
        self.assertIn("scheme_name", meta)
        self.assertIn("category", meta)
        self.assertIn("last_scraped_date", meta)

    def test_has_structured_fields(self):
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        sf = result["structured_fields"]
        self.assertEqual(sf["expense_ratio"], 1.04)
        self.assertEqual(sf["min_sip_investment"], 100)
        self.assertIn("NIFTY", sf["benchmark"])

    def test_has_faqs(self):
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        self.assertGreater(len(result["faqs"]), 0)

    def test_no_html_tags_in_text(self):
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        import re
        self.assertIsNone(re.search(r"<(?:script|style|div|span|p|nav|footer)[>\s]", result["text"]))

    def test_empty_html_handled(self):
        result = parse_html("", "https://groww.in/mutual-funds/test", "test")
        self.assertEqual(result["text"], "")

    def test_text_contains_faq_fields(self):
        """Text should contain key FAQ fields like expense ratio, exit load, etc."""
        result = parse_html(
            SAMPLE_HTML,
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "hdfc-large-cap-fund-direct-growth"
        )
        text = result["text"]
        self.assertIn("Expense Ratio", text)
        self.assertIn("Exit Load", text)
        self.assertIn("Minimum SIP", text)
        self.assertIn("Riskometer", text)
        self.assertIn("Benchmark", text)
        self.assertIn("Lock-in", text)


class TestParseAllIntegration(unittest.TestCase):
    """Integration test using actual scraped HTML files (if available)."""

    @unittest.skipUnless(
        os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "hdfc-large-cap-fund-direct-growth.html")),
        "Raw HTML files not available (run scraper first)"
    )
    def test_parse_all_produces_5_files(self):
        results = parse_all()
        success = [r for r in results if r["status"] == "success"]
        self.assertEqual(len(success), 5)

    @unittest.skipUnless(
        os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "hdfc-large-cap-fund-direct-growth.html")),
        "Raw HTML files not available (run scraper first)"
    )
    def test_parsed_files_have_required_fields(self):
        results = parse_all()
        processed_dir = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
        for r in results:
            if r["status"] == "success":
                with open(r["filepath"], "r") as f:
                    doc = json.load(f)
                self.assertGreater(len(doc["text"]), 50, f"Text too short for {r['slug']}")
                self.assertIn("source_url", doc["metadata"])
                self.assertIn("scheme_name", doc["metadata"])
                self.assertIn("category", doc["metadata"])
                self.assertIn("last_scraped_date", doc["metadata"])


if __name__ == "__main__":
    unittest.main()
