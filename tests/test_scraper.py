"""
Unit tests for the scraper module.

Tests:
- URL list integrity
- Slug extraction
- HTML fetching (mocked)
- File saving
- Error handling
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.ingestion.scraper import (
    URLS,
    scrape_url,
    scrape_all,
    _url_to_slug,
    RAW_DATA_DIR,
)


class TestURLList(unittest.TestCase):
    """Test that the URL list is correctly configured."""

    def test_url_count(self):
        """URL list should have exactly 5 entries."""
        self.assertEqual(len(URLS), 5)

    def test_urls_are_groww(self):
        """All URLs should be Groww mutual fund pages."""
        for url in URLS:
            self.assertTrue(
                url.startswith("https://groww.in/mutual-funds/"),
                f"URL does not start with Groww prefix: {url}",
            )

    def test_urls_are_unique(self):
        """All URLs should be unique."""
        self.assertEqual(len(URLS), len(set(URLS)))

    def test_urls_contain_hdfc(self):
        """All URLs should be for HDFC schemes."""
        for url in URLS:
            self.assertIn("hdfc", url.lower(), f"URL missing 'hdfc': {url}")


class TestSlugExtraction(unittest.TestCase):
    """Test the URL-to-slug conversion."""

    def test_slug_from_url(self):
        url = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
        self.assertEqual(_url_to_slug(url), "hdfc-large-cap-fund-direct-growth")

    def test_slug_from_url_with_trailing_slash(self):
        url = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth/"
        self.assertEqual(_url_to_slug(url), "hdfc-mid-cap-fund-direct-growth")

    def test_all_slugs_are_unique(self):
        slugs = [_url_to_slug(url) for url in URLS]
        self.assertEqual(len(slugs), len(set(slugs)))


class TestScrapeURL(unittest.TestCase):
    """Test the scrape_url function with mocked HTTP responses."""

    @patch("src.ingestion.scraper.requests.get")
    def test_successful_fetch(self, mock_get):
        """scrape_url should return HTML on a successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = scrape_url("https://groww.in/mutual-funds/test-fund")
        self.assertIn("<html>", result)
        self.assertGreater(len(result), 0)

    @patch("src.ingestion.scraper.requests.get")
    def test_returns_non_empty_html(self, mock_get):
        """scrape_url should return non-empty content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><head><title>Fund Page</title></head><body>" + "x" * 1000 + "</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = scrape_url("https://groww.in/mutual-funds/test-fund")
        self.assertGreater(len(result), 500)

    @patch("src.ingestion.scraper.requests.get")
    @patch("src.ingestion.scraper.time.sleep")  # Don't actually sleep in tests
    def test_retry_on_timeout(self, mock_sleep, mock_get):
        """scrape_url should retry on timeout and succeed on later attempt."""
        import requests as req

        mock_get.side_effect = [
            req.exceptions.Timeout("Timed out"),
            MagicMock(
                status_code=200,
                text="<html>Success after retry</html>",
                raise_for_status=MagicMock(),
            ),
        ]

        result = scrape_url("https://groww.in/mutual-funds/test-fund")
        self.assertIn("Success after retry", result)
        self.assertEqual(mock_get.call_count, 2)

    @patch("src.ingestion.scraper.requests.get")
    @patch("src.ingestion.scraper.time.sleep")
    def test_all_retries_exhausted(self, mock_sleep, mock_get):
        """scrape_url should raise after all retries fail."""
        import requests as req

        mock_get.side_effect = req.exceptions.ConnectionError("Network down")

        with self.assertRaises(req.exceptions.RequestException):
            scrape_url("https://groww.in/mutual-funds/test-fund")

        self.assertEqual(mock_get.call_count, 3)  # MAX_RETRIES = 3

    @patch("src.ingestion.scraper.requests.get")
    def test_404_no_retry(self, mock_get):
        """scrape_url should not retry on 404 errors."""
        import requests as req

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        with self.assertRaises(req.exceptions.HTTPError):
            scrape_url("https://groww.in/mutual-funds/nonexistent-fund")

        self.assertEqual(mock_get.call_count, 1)  # No retries for 404


class TestScrapeAll(unittest.TestCase):
    """Test the scrape_all orchestrator function."""

    @patch("src.ingestion.scraper.scrape_url")
    @patch("src.ingestion.scraper._save_html")
    def test_scrape_all_returns_5_results(self, mock_save, mock_scrape):
        """scrape_all should return results for all 5 URLs."""
        mock_scrape.return_value = "<html>Mock HTML</html>"
        mock_save.return_value = "/mock/path.html"

        results = scrape_all()
        self.assertEqual(len(results), 5)

    @patch("src.ingestion.scraper.scrape_url")
    @patch("src.ingestion.scraper._save_html")
    def test_scrape_all_success_status(self, mock_save, mock_scrape):
        """All results should have status 'success' when fetches succeed."""
        mock_scrape.return_value = "<html>Mock HTML</html>"
        mock_save.return_value = "/mock/path.html"

        results = scrape_all()
        for r in results:
            self.assertEqual(r["status"], "success")

    @patch("src.ingestion.scraper.scrape_url")
    @patch("src.ingestion.scraper._save_html")
    def test_scrape_all_handles_failure_gracefully(self, mock_save, mock_scrape):
        """scrape_all should not crash when one URL fails."""
        import requests as req

        # First URL fails, rest succeed
        mock_scrape.side_effect = [
            req.exceptions.RequestException("Network error"),
            "<html>OK</html>",
            "<html>OK</html>",
            "<html>OK</html>",
            "<html>OK</html>",
        ]
        mock_save.return_value = "/mock/path.html"

        results = scrape_all()
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[1]["status"], "success")


if __name__ == "__main__":
    unittest.main()
