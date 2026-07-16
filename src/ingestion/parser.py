"""
Parser module for extracting clean text and structured metadata from scraped Groww HTML.

This module handles Phase 2 of the data ingestion pipeline:
- Extracts structured data from Groww's __NEXT_DATA__ JSON (Next.js SSR data)
- Falls back to BeautifulSoup HTML parsing if __NEXT_DATA__ is unavailable
- Builds clean text blocks optimized for FAQ retrieval
- Extracts key fields: expense ratio, exit load, SIP amount, benchmark, riskometer, etc.
- Saves parsed output as JSON to data/processed/
"""

from __future__ import annotations

import os
import json
import re
import logging
from datetime import date
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")
PROCESSED_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")

# ---------------------------------------------------------------------------
# Scheme Map — URL slug → (display name, category)
# ---------------------------------------------------------------------------
SCHEME_MAP = {
    "hdfc-large-cap-fund-direct-growth": ("HDFC Large Cap Fund", "Large Cap"),
    "hdfc-mid-cap-fund-direct-growth": ("HDFC Mid Cap Fund", "Mid Cap"),
    "hdfc-small-cap-fund-direct-growth": ("HDFC Small Cap Fund", "Small Cap"),
    "hdfc-gold-etf-fund-of-fund-direct-plan-growth": ("HDFC Gold ETF FoF", "Gold"),
    "hdfc-silver-etf-fof-direct-growth": ("HDFC Silver ETF FoF", "Silver"),
}

# Source URL prefix
GROWW_BASE = "https://groww.in/mutual-funds/"


def _extract_next_data(soup: BeautifulSoup) -> dict | None:
    """
    Extract the __NEXT_DATA__ JSON from a Groww page.

    Groww uses Next.js, which embeds all server-side rendered data in a
    <script id="__NEXT_DATA__"> tag. This is the most reliable data source.

    Returns:
        The mfServerSideData dict, or None if not found.
    """
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        logger.warning("__NEXT_DATA__ not found in HTML.")
        return None

    try:
        data = json.loads(script.string)
        mf_data = data.get("props", {}).get("pageProps", {}).get("mfServerSideData", {})
        if not mf_data:
            logger.warning("mfServerSideData not found in __NEXT_DATA__.")
            return None
        return mf_data
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse __NEXT_DATA__: %s", e)
        return None


def _extract_structured_fields(mf_data: dict) -> dict:
    """
    Extract FAQ-relevant structured fields from mfServerSideData.

    Fields targeted per FAQ Assistant Requirements:
    - Expense ratio
    - Exit load details
    - Minimum SIP amount
    - ELSS lock-in period
    - Riskometer classification
    - Benchmark index
    - NAV and fund size
    - Fund manager, launch date, etc.
    """
    lock_in = mf_data.get("lock_in", {}) or {}
    lock_in_str = _format_lock_in(lock_in)

    return {
        # Core identity
        "scheme_name": mf_data.get("scheme_name", ""),
        "fund_name": mf_data.get("fund_name", ""),
        "fund_house": mf_data.get("fund_house", ""),
        "category": mf_data.get("category", ""),
        "plan_type": mf_data.get("plan_type", ""),
        "scheme_type": mf_data.get("scheme_type", ""),
        "description": mf_data.get("description", ""),
        "isin": mf_data.get("isin", ""),

        # FAQ-critical fields
        "expense_ratio": mf_data.get("expense_ratio"),
        "exit_load": mf_data.get("exit_load", ""),
        "min_sip_investment": mf_data.get("min_sip_investment"),
        "min_investment_amount": mf_data.get("min_investment_amount"),
        "riskometer": mf_data.get("nfo_risk", ""),
        "benchmark": mf_data.get("benchmark_name", "") or mf_data.get("benchmark", ""),
        "lock_in": lock_in_str,

        # Additional context
        "nav": mf_data.get("nav"),
        "nav_date": mf_data.get("nav_date", ""),
        "aum": mf_data.get("aum"),
        "fund_manager": mf_data.get("fund_manager", ""),
        "launch_date": mf_data.get("launch_date", ""),
        "groww_rating": mf_data.get("groww_rating"),
        "lumpsum_allowed": mf_data.get("lumpsum_allowed"),
        "max_sip_investment": mf_data.get("max_sip_investment"),
        "min_withdrawal": mf_data.get("min_withdrawal"),
        "registrar_agent": mf_data.get("registrar_agent", ""),
    }


def _format_lock_in(lock_in: dict) -> str:
    """
    Format the lock-in period from the structured data.

    Returns a human-readable string like '3 years' or 'No lock-in period'.
    """
    years = lock_in.get("years")
    months = lock_in.get("months")
    days = lock_in.get("days")

    parts = []
    if years:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days > 1 else ''}")

    return ", ".join(parts) if parts else "No lock-in period"


def _extract_faq_schema(soup: BeautifulSoup) -> list[dict]:
    """
    Extract FAQ entries from schema.org FAQPage JSON-LD.

    Returns:
        A list of dicts with 'question' and 'answer' keys.
    """
    faqs = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if data.get("@type") == "FAQPage":
                for entry in data.get("mainEntity", []):
                    question = entry.get("name", "")
                    answer_html = entry.get("acceptedAnswer", {}).get("text", "")
                    # Strip HTML from answer
                    answer_soup = BeautifulSoup(answer_html, "html.parser")
                    answer = answer_soup.get_text(separator=" ", strip=True)
                    if question and answer:
                        faqs.append({"question": question, "answer": answer})
        except (json.JSONDecodeError, KeyError):
            continue
    return faqs


def _build_clean_text(structured_fields: dict, faqs: list[dict], html_text: str) -> str:
    """
    Build a single clean text block optimized for chunking and retrieval.

    Combines:
    1. Structured field summaries (natural-language sentences)
    2. FAQ Q&A pairs from schema.org
    3. Cleaned HTML body text (fallback content)

    The result is a coherent text document that a chunker can split effectively.
    """
    sections = []
    sf = structured_fields

    # --- Section 1: Scheme Overview ---
    overview_parts = []
    name = sf.get("scheme_name") or sf.get("fund_name") or "Unknown Scheme"
    overview_parts.append(f"Scheme: {name}")

    if sf.get("fund_house"):
        overview_parts.append(f"Fund House: {sf['fund_house']}")
    if sf.get("category"):
        overview_parts.append(f"Category: {sf['category']}")
    if sf.get("plan_type"):
        overview_parts.append(f"Plan Type: {sf['plan_type']}")
    if sf.get("description"):
        overview_parts.append(f"Objective: {sf['description']}")
    if sf.get("launch_date"):
        overview_parts.append(f"Launch Date: {sf['launch_date']}")
    if sf.get("fund_manager"):
        overview_parts.append(f"Fund Manager: {sf['fund_manager']}")
    if sf.get("isin"):
        overview_parts.append(f"ISIN: {sf['isin']}")
    if sf.get("registrar_agent"):
        overview_parts.append(f"Registrar Agent: {sf['registrar_agent']}")

    sections.append("Scheme Overview\n" + "\n".join(overview_parts))

    # --- Section 2: Key Facts (FAQ-targeted) ---
    facts = []
    if sf.get("expense_ratio") is not None:
        facts.append(f"Expense Ratio: {sf['expense_ratio']}%")
    if sf.get("exit_load"):
        facts.append(f"Exit Load: {sf['exit_load']}")
    if sf.get("min_sip_investment") is not None:
        facts.append(f"Minimum SIP Amount: ₹{sf['min_sip_investment']}")
    if sf.get("min_investment_amount") is not None:
        facts.append(f"Minimum Lumpsum Investment: ₹{sf['min_investment_amount']}")
    if sf.get("riskometer"):
        facts.append(f"Riskometer Classification: {sf['riskometer']}")
    if sf.get("benchmark"):
        facts.append(f"Benchmark Index: {sf['benchmark']}")
    if sf.get("lock_in"):
        facts.append(f"Lock-in Period: {sf['lock_in']}")
    if sf.get("nav") is not None:
        facts.append(f"NAV: ₹{sf['nav']} (as of {sf.get('nav_date', 'N/A')})")
    if sf.get("aum") is not None:
        facts.append(f"Fund Size (AUM): ₹{sf['aum']} Cr")
    if sf.get("groww_rating") is not None:
        facts.append(f"Groww Rating: {sf['groww_rating']}/5")
    if sf.get("lumpsum_allowed") is not None:
        facts.append(f"Lumpsum Investment Allowed: {'Yes' if sf['lumpsum_allowed'] else 'No'}")
    if sf.get("min_withdrawal") is not None:
        facts.append(f"Minimum Withdrawal: ₹{sf['min_withdrawal']}")

    if facts:
        sections.append("Key Facts\n" + "\n".join(facts))

    # --- Section 3: FAQ Q&A ---
    if faqs:
        faq_text = []
        for faq in faqs:
            faq_text.append(f"Q: {faq['question']}\nA: {faq['answer']}")
        sections.append("Frequently Asked Questions\n" + "\n\n".join(faq_text))

    # --- Section 4: Additional content from HTML ---
    # Use cleaned HTML text as supplementary content
    if html_text and len(html_text) > 100:
        sections.append("Additional Information\n" + html_text)

    return "\n\n---\n\n".join(sections)


def _clean_html_text(soup: BeautifulSoup) -> str:
    """
    Extract clean body text from HTML, stripping boilerplate elements.

    Removes: scripts, styles, nav, footer, header, noscript, svg, button, form.
    """
    # Remove unwanted elements
    for tag_name in ["script", "style", "nav", "footer", "header", "noscript", "svg", "button", "form", "iframe"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Get text with space separator
    text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    # Remove very short lines (likely UI elements)
    lines = text.split("\n")
    cleaned_lines = [line for line in lines if len(line.strip()) > 3]
    text = "\n".join(cleaned_lines)

    return text.strip()


def extract_metadata(source_url: str, slug: str) -> dict:
    """
    Build metadata dict for a scheme from its URL and slug.

    Args:
        source_url: The full Groww URL.
        slug: The URL slug (e.g., 'hdfc-large-cap-fund-direct-growth').

    Returns:
        Metadata dict with source_url, scheme_name, category, last_scraped_date.
    """
    scheme_name, category = SCHEME_MAP.get(slug, ("Unknown", "Unknown"))

    return {
        "source_url": source_url,
        "scheme_name": scheme_name,
        "category": category,
        "last_scraped_date": date.today().isoformat(),
    }


def parse_html(html_content: str, source_url: str, slug: str) -> dict:
    """
    Parse raw HTML content from a Groww scheme page.

    Extraction strategy:
    1. Try __NEXT_DATA__ JSON first (most reliable, structured data)
    2. Extract FAQ schema.org JSON-LD
    3. Fall back to BeautifulSoup text extraction

    Args:
        html_content: Raw HTML string.
        source_url: The original URL of the page.
        slug: The URL slug for scheme mapping.

    Returns:
        Dict with keys: text, metadata, structured_fields, faqs
    """
    if not html_content or len(html_content) < 100:
        logger.warning("HTML content is empty or too short for %s", source_url)
        return {
            "text": "",
            "metadata": extract_metadata(source_url, slug),
            "structured_fields": {},
            "faqs": [],
        }

    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Extract structured data from __NEXT_DATA__
    mf_data = _extract_next_data(soup)
    structured_fields = _extract_structured_fields(mf_data) if mf_data else {}

    # Update metadata with data from __NEXT_DATA__ if available
    metadata = extract_metadata(source_url, slug)
    if mf_data:
        # Override scheme_name from data if available (more accurate)
        if mf_data.get("fund_name"):
            metadata["scheme_name"] = mf_data["fund_name"]
        if mf_data.get("category"):
            metadata["category"] = mf_data["category"]

    # 2. Extract FAQ schema.org
    faqs = _extract_faq_schema(soup)

    # 3. Clean HTML text (supplementary)
    html_text = _clean_html_text(soup)

    # 4. Build unified clean text
    text = _build_clean_text(structured_fields, faqs, html_text)

    # Guard: check minimum text length
    if len(text) < 50:
        logger.warning(
            "Parsed text is very short (%d chars) for %s. Page structure may have changed.",
            len(text),
            source_url,
        )

    logger.info(
        "Parsed %s: %d chars text, %d structured fields, %d FAQs",
        slug,
        len(text),
        len(structured_fields),
        len(faqs),
    )

    return {
        "text": text,
        "metadata": metadata,
        "structured_fields": structured_fields,
        "faqs": faqs,
    }


def parse_all() -> list[dict]:
    """
    Parse all raw HTML files from data/raw/ and save results to data/processed/.

    Returns:
        A list of result dicts with keys: slug, status, filepath, error.
    """
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    raw_dir = os.path.normpath(RAW_DATA_DIR)
    html_files = [f for f in os.listdir(raw_dir) if f.endswith(".html")]

    if not html_files:
        logger.warning("No HTML files found in %s", raw_dir)
        return []

    results = []

    for filename in sorted(html_files):
        slug = filename.replace(".html", "")
        source_url = GROWW_BASE + slug
        filepath_in = os.path.join(raw_dir, filename)
        filepath_out = os.path.join(PROCESSED_DATA_DIR, f"{slug}.json")

        result = {
            "slug": slug,
            "status": "failed",
            "filepath": None,
            "error": None,
        }

        try:
            with open(filepath_in, "r", encoding="utf-8") as f:
                html_content = f.read()

            if not html_content:
                result["error"] = "Empty HTML file"
                logger.warning("Empty HTML file: %s", filepath_in)
                results.append(result)
                continue

            parsed = parse_html(html_content, source_url, slug)

            # Save to JSON
            with open(filepath_out, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)

            result["status"] = "success"
            result["filepath"] = filepath_out
            logger.info("Saved parsed output to %s", filepath_out)

        except Exception as e:
            result["error"] = str(e)
            logger.error("Failed to parse %s: %s", filename, e)

        results.append(result)

    # Summary
    success = sum(1 for r in results if r["status"] == "success")
    logger.info("Parsing complete: %d/%d succeeded", success, len(results))

    return results


if __name__ == "__main__":
    parse_all()
