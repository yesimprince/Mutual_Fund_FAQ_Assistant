"""
Chunker module for creating semantically meaningful chunks from parsed mutual fund data.

This module handles Phase 3 of the data ingestion pipeline (Phase 4 in the implementation plan):
- Creates structured-facts chunks from the structured_fields JSON
- Creates one chunk per FAQ from the faqs array (preserves Q+A integrity)
- Creates section-based chunks from the clean text sections (Overview, Key Facts only)
- Discards "Additional Information" boilerplate (Groww navigation, other fund listings, etc.)
- Saves all chunks as JSONL to data/chunks/

Chunking Strategy — 4 Chunk Types:
  1. structured_facts: One per scheme, natural-language summary of key-value facts
  2. faq: One per FAQ Q&A pair, preserving question-answer integrity
  3. section (scheme_overview): The scheme overview narrative text
  4. section (key_facts): The key facts narrative text

Expected output: ~11 chunks per scheme × 5 schemes = ~55 total chunks
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROCESSED_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")
CHUNKS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chunks")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_CHUNK_TOKENS = 500
# Approximate: 1 token ≈ 4 characters (conservative estimate for English text)
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * 4

# Sections to keep from the text field (split by "---" delimiter)
SECTION_NAMES = ["Scheme Overview", "Key Facts"]

# Sections to discard
DISCARD_SECTIONS = ["Frequently Asked Questions", "Additional Information"]


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count from text using a simple whitespace heuristic.

    This is a rough approximation — 1 token ≈ 0.75 words for English text.
    Good enough for chunk size enforcement without requiring a tokenizer dependency.
    """
    return len(text.split())


def _split_text_fallback(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """
    Simple recursive character splitter as a fallback for oversized sections.

    Splits on paragraph breaks, then newlines, then sentences, then spaces.
    Uses token estimation (word count) for size checks.

    Args:
        text: The text to split.
        chunk_size: Maximum tokens per chunk.
        chunk_overlap: Token overlap between consecutive chunks.

    Returns:
        A list of text chunks.
    """
    if _estimate_tokens(text) <= chunk_size:
        return [text]

    separators = ["\n\n", "\n", ". ", " "]
    chunks = []

    for sep in separators:
        parts = text.split(sep)
        if len(parts) <= 1:
            continue

        current_chunk = ""
        for part in parts:
            candidate = current_chunk + sep + part if current_chunk else part
            if _estimate_tokens(candidate) <= chunk_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = part

        if current_chunk:
            chunks.append(current_chunk.strip())

        if chunks:
            return chunks

    # Last resort: hard split by characters
    char_limit = chunk_size * 4  # ~4 chars per token
    return [text[i:i + char_limit] for i in range(0, len(text), char_limit - chunk_overlap * 4)]


def build_structured_facts_chunk(doc: dict) -> dict | None:
    """
    Build a single structured-facts chunk from the structured_fields JSON.

    Formats the key-value pairs into a natural-language paragraph optimized
    for embedding and retrieval. This chunk contains the most FAQ-relevant
    facts: expense ratio, exit load, NAV, AUM, SIP amounts, riskometer, etc.

    Args:
        doc: The parsed document dict containing 'structured_fields' and 'metadata'.

    Returns:
        A chunk dict, or None if structured_fields is empty.
    """
    sf = doc.get("structured_fields", {})
    if not sf:
        logger.warning("No structured_fields found in document")
        return None

    scheme_name = sf.get("scheme_name") or sf.get("fund_name") or "Unknown Scheme"

    # Build natural-language lines from the structured fields
    lines = [f"{scheme_name} — Key Facts:"]

    field_mappings = [
        ("fund_house", "Fund House"),
        ("category", "Category"),
        ("plan_type", "Plan Type"),
        ("description", "Investment Objective"),
    ]
    for key, label in field_mappings:
        if sf.get(key):
            lines.append(f"{label}: {sf[key]}.")

    # Financial metrics — the core FAQ-targeted fields
    if sf.get("expense_ratio") is not None:
        lines.append(f"Expense Ratio: {sf['expense_ratio']}%.")
    if sf.get("exit_load"):
        lines.append(f"Exit Load: {sf['exit_load']}")
    if sf.get("min_sip_investment") is not None:
        lines.append(f"Minimum SIP Amount: ₹{sf['min_sip_investment']}.")
    if sf.get("min_investment_amount") is not None:
        lines.append(f"Minimum Lumpsum Investment: ₹{sf['min_investment_amount']}.")
    if sf.get("nav") is not None:
        nav_date = sf.get("nav_date", "N/A")
        lines.append(f"NAV: ₹{sf['nav']} (as of {nav_date}).")
    if sf.get("aum") is not None:
        lines.append(f"Fund Size (AUM): ₹{sf['aum']} Cr.")
    if sf.get("riskometer"):
        lines.append(f"Riskometer Classification: {sf['riskometer']}.")
    if sf.get("benchmark"):
        lines.append(f"Benchmark Index: {sf['benchmark']}.")
    if sf.get("lock_in"):
        lines.append(f"Lock-in Period: {sf['lock_in']}.")
    if sf.get("fund_manager"):
        lines.append(f"Fund Manager: {sf['fund_manager']}.")
    if sf.get("launch_date"):
        lines.append(f"Launch Date: {sf['launch_date']}.")
    if sf.get("isin"):
        lines.append(f"ISIN: {sf['isin']}.")
    if sf.get("groww_rating") is not None:
        lines.append(f"Groww Rating: {sf['groww_rating']}/5.")
    if sf.get("lumpsum_allowed") is not None:
        lines.append(f"Lumpsum Investment Allowed: {'Yes' if sf['lumpsum_allowed'] else 'No'}.")
    if sf.get("min_withdrawal") is not None:
        lines.append(f"Minimum Withdrawal: ₹{sf['min_withdrawal']}.")
    if sf.get("registrar_agent"):
        lines.append(f"Registrar & Transfer Agent: {sf['registrar_agent']}.")

    text = " ".join(lines)

    return {
        "text": text,
        "chunk_type": "structured_facts",
        "section_heading": "Key Facts",
    }


def build_faq_chunks(doc: dict) -> list[dict]:
    """
    Build one chunk per FAQ pair from the faqs array.

    Each chunk preserves the complete Q&A pair to ensure that retrieval
    returns the full answer alongside its question. This prevents the
    common RAG failure of splitting a question from its answer.

    Args:
        doc: The parsed document dict containing 'faqs'.

    Returns:
        A list of chunk dicts, one per FAQ.
    """
    faqs = doc.get("faqs", [])
    if not faqs:
        logger.warning("No FAQs found in document")
        return []

    chunks = []
    for i, faq in enumerate(faqs):
        question = faq.get("question", "").strip()
        answer = faq.get("answer", "").strip()

        if not question or not answer:
            logger.warning("Skipping FAQ with missing Q or A at index %d", i)
            continue

        text = f"Q: {question}\nA: {answer}"

        chunks.append({
            "text": text,
            "chunk_type": "faq",
            "section_heading": "FAQ",
            "faq_index": i,
        })

    return chunks


def _identify_section(section_text: str) -> str | None:
    """
    Identify which section a text block belongs to based on its heading.

    Returns the section name if it's a section we want to keep, or None
    if it should be discarded.
    """
    first_line = section_text.strip().split("\n")[0].strip() if section_text.strip() else ""

    for name in SECTION_NAMES:
        if first_line.lower().startswith(name.lower()):
            return name

    # Check if it's a section to explicitly discard
    for name in DISCARD_SECTIONS:
        if first_line.lower().startswith(name.lower()):
            return None

    return None


def build_section_chunks(doc: dict) -> list[dict]:
    """
    Build section-based chunks from the text field.

    Splits the text on '---' delimiters and keeps only the "Scheme Overview"
    and "Key Facts" sections. Discards "Frequently Asked Questions" (already
    covered by FAQ chunks) and "Additional Information" (Groww boilerplate).

    If a kept section exceeds ~500 tokens, applies a recursive character
    splitter as a fallback.

    Args:
        doc: The parsed document dict containing 'text'.

    Returns:
        A list of chunk dicts.
    """
    text = doc.get("text", "")
    if not text:
        logger.warning("No text field found in document")
        return []

    # Split on the --- delimiter used by the parser
    raw_sections = text.split("\n\n---\n\n")

    chunks = []
    for raw_section in raw_sections:
        section_text = raw_section.strip()
        if not section_text:
            continue

        section_name = _identify_section(section_text)
        if section_name is None:
            # This is either a discard section or unrecognized — skip it
            continue

        # Check if the section needs further splitting
        if _estimate_tokens(section_text) > MAX_CHUNK_TOKENS:
            sub_chunks = _split_text_fallback(section_text)
            for j, sub_text in enumerate(sub_chunks):
                chunks.append({
                    "text": sub_text.strip(),
                    "chunk_type": "section",
                    "section_heading": section_name,
                    "sub_chunk_index": j,
                })
        else:
            chunks.append({
                "text": section_text,
                "chunk_type": "section",
                "section_heading": section_name,
            })

    return chunks


def chunk_document(parsed_doc: dict) -> list[dict]:
    """
    Create all chunks for a single parsed document.

    Orchestrates the three chunk-building strategies:
    1. Structured facts chunk (from structured_fields)
    2. FAQ chunks (from faqs array)
    3. Section chunks (from text field, filtered)

    Each chunk receives:
    - A unique chunk_id: {scheme_slug}_{chunk_type}_{index}
    - Parent metadata: source_url, scheme_name, category, last_scraped_date

    Args:
        parsed_doc: The full parsed document dict.

    Returns:
        A list of chunk dicts with text, metadata, chunk_id, and chunk_type.
    """
    metadata = parsed_doc.get("metadata", {})
    source_url = metadata.get("source_url", "")

    # Derive scheme slug from source URL for chunk_id generation
    slug = source_url.rstrip("/").split("/")[-1] if source_url else "unknown"

    all_chunks = []

    # --- Chunk Type 1: Structured Facts ---
    sf_chunk = build_structured_facts_chunk(parsed_doc)
    if sf_chunk:
        all_chunks.append(sf_chunk)

    # --- Chunk Type 2: FAQ Pairs ---
    faq_chunks = build_faq_chunks(parsed_doc)
    all_chunks.extend(faq_chunks)

    # --- Chunk Types 3 & 4: Section-based ---
    section_chunks = build_section_chunks(parsed_doc)
    all_chunks.extend(section_chunks)

    # Attach metadata and assign unique chunk_ids
    # Track counts per chunk_type for ID generation
    type_counters: dict[str, int] = {}

    for chunk in all_chunks:
        chunk_type = chunk.get("chunk_type", "unknown")
        idx = type_counters.get(chunk_type, 0)
        type_counters[chunk_type] = idx + 1

        chunk["chunk_id"] = f"{slug}_{chunk_type}_{idx}"
        chunk["source_url"] = metadata.get("source_url", "")
        chunk["scheme_name"] = metadata.get("scheme_name", "")
        chunk["category"] = metadata.get("category", "")
        chunk["last_scraped_date"] = metadata.get("last_scraped_date", "")

    return all_chunks


def chunk_all() -> list[dict]:
    """
    Chunk all parsed JSON files from data/processed/ and save to data/chunks/.

    Each scheme gets its own JSONL file (e.g., data/chunks/hdfc-large-cap-fund-direct-growth.jsonl),
    mirroring the per-scheme structure in data/processed/.

    Returns:
        A list of result dicts with keys: slug, status, chunk_count, filepath, error.
    """
    os.makedirs(CHUNKS_DATA_DIR, exist_ok=True)

    processed_dir = os.path.normpath(PROCESSED_DATA_DIR)
    json_files = [f for f in os.listdir(processed_dir) if f.endswith(".json")]

    if not json_files:
        logger.warning("No JSON files found in %s", processed_dir)
        return []

    results = []

    for filename in sorted(json_files):
        slug = filename.replace(".json", "")
        filepath = os.path.join(processed_dir, filename)

        result = {
            "slug": slug,
            "status": "failed",
            "chunk_count": 0,
            "filepath": None,
            "error": None,
        }

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                parsed_doc = json.load(f)

            chunks = chunk_document(parsed_doc)

            # Write per-scheme JSONL file
            output_path = os.path.join(CHUNKS_DATA_DIR, f"{slug}.jsonl")
            with open(output_path, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

            result["status"] = "success"
            result["chunk_count"] = len(chunks)
            result["filepath"] = output_path
            logger.info(
                "Chunked %s: %d chunks (1 structured_facts, %d faqs, %d sections) → %s",
                slug,
                len(chunks),
                sum(1 for c in chunks if c["chunk_type"] == "faq"),
                sum(1 for c in chunks if c["chunk_type"] == "section"),
                output_path,
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error("Failed to chunk %s: %s", filename, e)

        results.append(result)

    # Summary
    total_chunks = sum(r["chunk_count"] for r in results)
    success = sum(1 for r in results if r["status"] == "success")
    logger.info(
        "Chunking complete: %d/%d schemes processed, %d total chunks",
        success,
        len(results),
        total_chunks,
    )

    return results


if __name__ == "__main__":
    chunk_all()
