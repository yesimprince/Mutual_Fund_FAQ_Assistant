"""
Scraper module for fetching raw HTML from Groww mutual fund scheme pages.

This module handles Phase 1 of the data ingestion pipeline:
- Fetches HTML content from each Groww scheme URL
- Implements retry logic with exponential backoff
- Saves raw HTML files to data/raw/
"""

import os
import time
import logging
from urllib.parse import urlparse

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source URLs — 5 HDFC Mutual Fund scheme pages on Groww
# ---------------------------------------------------------------------------
URLS = [
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth",
    "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")
MAX_RETRIES = 3
TIMEOUT_SECONDS = 10
RETRY_BACKOFF_BASE = 2  # seconds — exponential: 2, 4, 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _url_to_slug(url: str) -> str:
    """
    Extract a filesystem-safe slug from a Groww URL.

    Example:
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
        → "hdfc-large-cap-fund-direct-growth"
    """
    path = urlparse(url).path  # e.g. /mutual-funds/hdfc-large-cap-...
    slug = path.strip("/").split("/")[-1]
    return slug


def scrape_url(url: str) -> str:
    """
    Fetch raw HTML from a single URL with retry logic.

    Args:
        url: The Groww scheme page URL to fetch.

    Returns:
        The raw HTML content as a string.

    Raises:
        requests.RequestException: If all retries are exhausted.
    """
    last_exception = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Fetching %s (attempt %d/%d)", url, attempt, MAX_RETRIES)
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()

            html = response.text

            # Guard: detect JS-rendered / CAPTCHA pages with very little content
            if len(html) < 500:
                logger.warning(
                    "Response for %s is suspiciously short (%d chars). "
                    "The page may require JavaScript rendering.",
                    url,
                    len(html),
                )

            logger.info(
                "Successfully fetched %s (%d chars)", url, len(html)
            )
            return html

        except requests.exceptions.Timeout:
            last_exception = TimeoutError(f"Timeout fetching {url}")
            logger.warning("Timeout on attempt %d for %s", attempt, url)

        except requests.exceptions.HTTPError as e:
            last_exception = e
            status = e.response.status_code if e.response is not None else "unknown"
            logger.warning(
                "HTTP %s on attempt %d for %s", status, attempt, url
            )
            # Don't retry on 404 — page doesn't exist
            if e.response is not None and e.response.status_code == 404:
                logger.error("404 Not Found for %s — skipping retries.", url)
                raise

        except requests.exceptions.ConnectionError as e:
            last_exception = e
            logger.warning("Connection error on attempt %d for %s", attempt, url)

        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning("Request error on attempt %d for %s: %s", attempt, url, e)

        # Exponential backoff before next retry
        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE ** attempt
            logger.info("Retrying in %ds...", wait)
            time.sleep(wait)

    # All retries exhausted
    logger.error("All %d retries failed for %s", MAX_RETRIES, url)
    raise requests.exceptions.RequestException(
        f"Failed to fetch {url} after {MAX_RETRIES} retries"
    ) from last_exception


def _save_html(slug: str, html: str) -> str:
    """
    Save raw HTML content to data/raw/<slug>.html.

    Returns:
        The absolute path to the saved file.
    """
    # Ensure output directory exists
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    filepath = os.path.join(RAW_DATA_DIR, f"{slug}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Saved HTML to %s", filepath)
    return filepath


def scrape_all() -> list[dict]:
    """
    Scrape all Groww scheme URLs and save raw HTML to data/raw/.

    Returns:
        A list of dicts, one per URL, with keys:
        - url: the source URL
        - slug: the extracted slug
        - filepath: path to saved HTML file
        - status: "success" or "failed"
        - error: error message (if failed)
        - content_length: character count of HTML (if success)
    """
    results = []

    for url in URLS:
        slug = _url_to_slug(url)
        result = {
            "url": url,
            "slug": slug,
            "filepath": None,
            "status": "failed",
            "error": None,
            "content_length": 0,
        }

        try:
            html = scrape_url(url)
            filepath = _save_html(slug, html)
            result["filepath"] = filepath
            result["status"] = "success"
            result["content_length"] = len(html)

        except Exception as e:
            result["error"] = str(e)
            logger.error("Failed to scrape %s: %s", url, e)

        results.append(result)

    # Print summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    logger.info(
        "Scraping complete: %d/%d succeeded, %d failed",
        success,
        len(URLS),
        failed,
    )

    return results


if __name__ == "__main__":
    scrape_all()
