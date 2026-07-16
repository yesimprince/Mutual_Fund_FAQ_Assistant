"""
Query Classifier for the Mutual Fund FAQ Assistant.

Classifies user queries into one of three categories:
    - "factual"      — Answerable from the mutual fund corpus
    - "advisory"     — Investment advice / opinion (should be refused)
    - "pii_detected" — Contains personally identifiable information (should be blocked)

Classification approach: Hybrid (keyword blocklist + regex patterns).
No LLM fallback — conserves Groq rate budget.
"""

from __future__ import annotations

import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Advisory keyword blocklist (case-insensitive substring match)
# ---------------------------------------------------------------------------
ADVISORY_KEYWORDS = [
    "should i",
    "which is better",
    "recommend",
    "suggest",
    "advise",
    "good fund",
    "best fund",
    "invest in",
    "worth investing",
    "better option",
    "better choice",
    "opinion",
    "what do you think",
    "will it give",
    "will it perform",
    "expected return",
    "future return",
    "buy or sell",
    "hold or sell",
    "compare",
    "comparison",
    "outperform",
]

# ---------------------------------------------------------------------------
# Advisory regex intent patterns
# ---------------------------------------------------------------------------
ADVISORY_PATTERNS = [
    # "is X a good fund" / "is X good"
    re.compile(r"\bis\b.*\b(good|bad|safe|risky|worth)\b.*\bfund\b", re.IGNORECASE),
    # "will X give returns" / "will X grow"
    re.compile(r"\bwill\b.*\b(give|grow|increase|rise|perform|beat)\b", re.IGNORECASE),
    # "X or Y which" / "X vs Y"
    re.compile(r"\b(?:which|what)\b.*\b(?:better|best|prefer)\b", re.IGNORECASE),
    re.compile(r"\bvs\.?\b", re.IGNORECASE),
    # "can I get X% return"
    re.compile(r"\b(?:can|will)\s+(?:i|we)\s+(?:get|earn|make)\b", re.IGNORECASE),
    # "is it safe to invest"
    re.compile(r"\bsafe\s+to\s+invest\b", re.IGNORECASE),
    # "how much return" / "how much profit"
    re.compile(r"\bhow\s+much\s+(?:return|profit|gain|money)\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# PII regex patterns
# ---------------------------------------------------------------------------
PII_PATTERNS = {
    "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(
        r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b"   # Indian mobile numbers
    ),
    "account_number": re.compile(r"\b\d{9,18}\b"),  # Bank account numbers (9-18 digits)
}

# Contextual keywords that indicate PII intent (used alongside PII patterns)
PII_CONTEXT_KEYWORDS = [
    "my pan", "pan number", "pan card", "pan is",
    "my aadhaar", "aadhaar number", "aadhaar card", "aadhaar is",
    "my email", "email is", "email id",
    "my phone", "phone number", "mobile number", "contact number", "contact me",
    "my account", "account number", "bank account",
    "my otp", "otp is",
]


def _has_pii(query: str) -> bool:
    """
    Detect PII in the query using regex patterns.

    Uses a two-tier approach:
    1. Direct PII pattern match (PAN, email — high confidence patterns)
    2. Numeric patterns (Aadhaar, phone, account) require contextual keyword
       to reduce false positives from fund amounts, NAV values, etc.

    Args:
        query: The user's input query.

    Returns:
        True if PII is detected, False otherwise.
    """
    query_lower = query.lower()

    # Tier 1: High-confidence patterns (PAN has a very specific format)
    if PII_PATTERNS["pan"].search(query):
        logger.info("PII detected: PAN card number")
        return True

    if PII_PATTERNS["email"].search(query):
        logger.info("PII detected: Email address")
        return True

    # Tier 2: Check for PII context keywords first, then verify with patterns
    has_pii_context = any(kw in query_lower for kw in PII_CONTEXT_KEYWORDS)

    if has_pii_context:
        if PII_PATTERNS["aadhaar"].search(query):
            logger.info("PII detected: Aadhaar number")
            return True
        if PII_PATTERNS["phone"].search(query):
            logger.info("PII detected: Phone number")
            return True
        if PII_PATTERNS["account_number"].search(query):
            logger.info("PII detected: Account number")
            return True

    return False


def _is_advisory(query: str) -> bool:
    """
    Check if the query is asking for investment advice or opinions.

    Args:
        query: The user's input query.

    Returns:
        True if advisory intent is detected, False otherwise.
    """
    query_lower = query.lower()

    # Check keyword blocklist (substring match)
    for keyword in ADVISORY_KEYWORDS:
        if keyword in query_lower:
            logger.info("Advisory keyword detected: '%s'", keyword)
            return True

    # Check regex intent patterns
    for pattern in ADVISORY_PATTERNS:
        if pattern.search(query):
            logger.info("Advisory pattern matched: %s", pattern.pattern[:50])
            return True

    return False


def classify(query: str) -> str:
    """
    Classify a user query into one of three categories.

    Classification order (first match wins):
        1. PII detection — highest priority (security concern)
        2. Advisory detection — medium priority (policy enforcement)
        3. Factual — default (answerable query)

    Args:
        query: The user's input query string.

    Returns:
        One of: "pii_detected", "advisory", or "factual".
    """
    if not query or not query.strip():
        logger.warning("Empty query received — classifying as factual")
        return "factual"

    query = query.strip()

    # 1. PII check (highest priority)
    if _has_pii(query):
        logger.info("Query classified as: pii_detected")
        return "pii_detected"

    # 2. Advisory check
    if _is_advisory(query):
        logger.info("Query classified as: advisory")
        return "advisory"

    # 3. Default: factual
    logger.info("Query classified as: factual")
    return "factual"
