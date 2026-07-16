"""
Guardrails module for the Mutual Fund FAQ Assistant.

Provides input and output safety checks:

Input Guardrails (pre-processing):
    - PII detection via regex (PAN, Aadhaar, phone, email)
    - Query length cap (500 characters)
    - Prompt injection stripping

Output Guardrails (post-processing):
    - Response sentence count check (≤ 3)
    - Citation URL presence check (exactly 1 Groww URL)
    - Advisory language scan in output
    - PII leak scan
    - Footer enforcement ("Last updated from sources: <date>")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_QUERY_LENGTH = 500
MAX_RESPONSE_SENTENCES = 3
GROWW_URL_PATTERN = re.compile(r"https?://(?:www\.)?groww\.in/\S+")
FOOTER_PREFIX = "Last updated from sources:"

# ---------------------------------------------------------------------------
# PII patterns (shared with query_classifier, but guardrails uses them for
# both input and output scanning)
# ---------------------------------------------------------------------------
PII_PATTERNS = {
    "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b"),
}

# ---------------------------------------------------------------------------
# Prompt injection patterns to strip from user input
# ---------------------------------------------------------------------------
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"ignore\s+(?:the\s+)?above", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above)", re.IGNORECASE),
    re.compile(r"forget\s+(?:all\s+)?(?:previous|prior|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?:a\s+)?", re.IGNORECASE),
    re.compile(r"pretend\s+(?:you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"new\s+(?:system\s+)?(?:prompt|instruction|role)", re.IGNORECASE),
    re.compile(r"override\s+(?:system|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
]

# Advisory language to scan for in LLM output
OUTPUT_ADVISORY_KEYWORDS = [
    "should invest",
    "should buy",
    "should sell",
    "i recommend",
    "i suggest",
    "i advise",
    "you should",
    "you could invest",
    "better investment",
    "strong buy",
    "guaranteed return",
]


# =========================================================================
# Input Guardrails
# =========================================================================

def check_query_length(query: str) -> tuple[bool, str]:
    """
    Check if the query exceeds the maximum allowed length.

    Args:
        query: The user's input query.

    Returns:
        (passed, message) — passed is True if within limits.
    """
    if len(query) > MAX_QUERY_LENGTH:
        logger.warning(
            "Query exceeds max length: %d > %d chars", len(query), MAX_QUERY_LENGTH
        )
        return False, (
            f"Your question is too long ({len(query)} characters). "
            f"Please keep it under {MAX_QUERY_LENGTH} characters."
        )
    return True, ""


def detect_pii_in_text(text: str) -> list[str]:
    """
    Scan text for PII patterns.

    Args:
        text: The text to scan.

    Returns:
        A list of PII types detected (e.g., ["pan", "email"]). Empty if clean.
    """
    detected = []
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            detected.append(pii_type)
    return detected


def strip_prompt_injections(query: str) -> str:
    """
    Remove prompt injection patterns from user input.

    Strips known injection phrases while preserving the rest of the query.
    This is a defense-in-depth measure — the LLM system prompt also
    constrains behavior.

    Args:
        query: The raw user input.

    Returns:
        The sanitized query with injection patterns removed.
    """
    sanitized = query
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("", sanitized)

    # Collapse multiple spaces left by stripping
    sanitized = re.sub(r"\s{2,}", " ", sanitized).strip()

    if sanitized != query.strip():
        logger.warning("Prompt injection patterns stripped from query")

    return sanitized


def apply_input_guardrails(query: str) -> tuple[str, Optional[str]]:
    """
    Apply all input guardrails to a user query.

    Checks in order:
        1. Query length cap
        2. PII detection
        3. Prompt injection stripping

    Args:
        query: The raw user input.

    Returns:
        (sanitized_query, error_message).
        - If error_message is None, the query is safe to process.
        - If error_message is not None, the query should be rejected.
    """
    if not query or not query.strip():
        return "", "Please enter a question."

    query = query.strip()

    # 1. Length check
    length_ok, length_msg = check_query_length(query)
    if not length_ok:
        return query, length_msg

    # 2. PII detection
    pii_types = detect_pii_in_text(query)
    if pii_types:
        logger.warning("PII detected in input: %s", pii_types)
        return query, (
            "For your security, please do not share personal information "
            "like PAN, Aadhaar, or account numbers. I cannot process such data."
        )

    # 3. Strip prompt injections (sanitize but don't reject)
    sanitized = strip_prompt_injections(query)

    return sanitized, None


# =========================================================================
# Output Guardrails
# =========================================================================

def check_sentence_count(response: str) -> str:
    """
    Ensure the response has at most MAX_RESPONSE_SENTENCES sentences.

    If exceeded, truncates to the maximum allowed sentences.

    Args:
        response: The LLM-generated response text.

    Returns:
        The response, truncated if necessary.
    """
    # Split on sentence-ending punctuation followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+', response.strip())

    # Filter out empty strings and the footer (which starts with "Last updated")
    content_sentences = [
        s for s in sentences
        if s.strip() and not s.strip().startswith(FOOTER_PREFIX)
    ]

    if len(content_sentences) > MAX_RESPONSE_SENTENCES:
        logger.warning(
            "Response has %d sentences, truncating to %d",
            len(content_sentences), MAX_RESPONSE_SENTENCES,
        )
        # Keep only the allowed number of sentences
        truncated = " ".join(content_sentences[:MAX_RESPONSE_SENTENCES])

        # Preserve footer if it was present
        footer_sentences = [
            s for s in sentences if s.strip().startswith(FOOTER_PREFIX)
        ]
        if footer_sentences:
            truncated += " " + footer_sentences[0]

        return truncated

    return response


def check_citation(response: str) -> tuple[bool, str]:
    """
    Verify that the response contains exactly one Groww citation URL.

    Args:
        response: The LLM-generated response text.

    Returns:
        (has_citation, citation_url).
        - has_citation is True if exactly one Groww URL is found.
        - citation_url is the found URL or an empty string.
    """
    urls = GROWW_URL_PATTERN.findall(response)
    if len(urls) == 1:
        return True, urls[0]
    elif len(urls) == 0:
        logger.warning("No citation URL found in response")
        return False, ""
    else:
        logger.warning("Multiple citation URLs found: %s", urls)
        # Return the first one — still acceptable but log the anomaly
        return True, urls[0]


def scan_advisory_language(response: str) -> list[str]:
    """
    Scan the LLM output for advisory/recommendation language.

    Args:
        response: The LLM-generated response text.

    Returns:
        A list of advisory phrases found. Empty if clean.
    """
    response_lower = response.lower()
    found = [kw for kw in OUTPUT_ADVISORY_KEYWORDS if kw in response_lower]
    if found:
        logger.warning("Advisory language detected in output: %s", found)
    return found


def enforce_footer(response: str, last_updated_date: str) -> str:
    """
    Ensure the response ends with the required footer.

    If the footer is missing, appends it.

    Args:
        response: The LLM-generated response text.
        last_updated_date: The date string for the footer.

    Returns:
        The response with the footer guaranteed.
    """
    expected_footer = f"{FOOTER_PREFIX} {last_updated_date}"

    if FOOTER_PREFIX in response:
        return response

    # Append footer
    response = response.rstrip()
    if not response.endswith((".", "!", "?")):
        response += "."
    response += f"\n\n{expected_footer}"

    return response


def apply_output_guardrails(
    response: str,
    last_updated_date: str,
) -> dict:
    """
    Apply all output guardrails to an LLM-generated response.

    Checks and fixes:
        1. Sentence count enforcement (truncate if > 3)
        2. Citation URL check
        3. Advisory language scan
        4. PII leak scan
        5. Footer enforcement

    Args:
        response: The raw LLM response text.
        last_updated_date: Date string for the footer.

    Returns:
        A dict with:
            - "response": The guardrail-processed response text
            - "citation_url": Extracted citation URL (or "")
            - "warnings": List of warning strings (if any)
            - "blocked": True if the response should be blocked
    """
    warnings = []
    blocked = False

    # 1. Sentence count
    response = check_sentence_count(response)

    # 2. Citation check
    has_citation, citation_url = check_citation(response)
    if not has_citation:
        warnings.append("No citation URL found in response")

    # 3. Advisory language scan
    advisory_phrases = scan_advisory_language(response)
    if advisory_phrases:
        warnings.append(f"Advisory language in output: {advisory_phrases}")

    # 4. PII leak scan
    pii_leaks = detect_pii_in_text(response)
    if pii_leaks:
        warnings.append(f"PII detected in output: {pii_leaks}")
        blocked = True
        response = (
            "I'm unable to provide this response due to a safety check. "
            "Please rephrase your question."
        )

    # 5. Footer enforcement
    if not blocked:
        response = enforce_footer(response, last_updated_date)

    return {
        "response": response,
        "citation_url": citation_url,
        "warnings": warnings,
        "blocked": blocked,
    }
