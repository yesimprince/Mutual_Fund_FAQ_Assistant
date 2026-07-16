"""
Generator module for the Mutual Fund FAQ Assistant.

Handles LLM response generation via Groq API with rate limiting:
    - generate_response(): Factual query → LLM-generated answer (rate-limited)
    - generate_refusal(): Advisory query → Template-based refusal (no API call)
    - generate_pii_block(): PII query → Block message (no API call)

Rate limiting is integrated via pre-flight can_request() and
post-flight record_request() calls to GroqRateLimiter.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from src.pipeline.rate_limiter import get_rate_limiter
from src.pipeline.guardrails import apply_output_guardrails

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = 0.1
MAX_TOKENS = 300

# Prompt template paths
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "system_prompt.txt"
REFUSAL_PROMPT_PATH = _PROMPTS_DIR / "refusal_prompt.txt"

# ---------------------------------------------------------------------------
# Prompt loading (cached)
# ---------------------------------------------------------------------------
_system_prompt_template: Optional[str] = None
_refusal_prompt_template: Optional[str] = None


def _load_system_prompt() -> str:
    """Load and cache the system prompt template."""
    global _system_prompt_template
    if _system_prompt_template is None:
        _system_prompt_template = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        logger.info("Loaded system prompt from %s", SYSTEM_PROMPT_PATH)
    return _system_prompt_template


def _load_refusal_prompt() -> str:
    """Load and cache the refusal prompt template."""
    global _refusal_prompt_template
    if _refusal_prompt_template is None:
        _refusal_prompt_template = REFUSAL_PROMPT_PATH.read_text(encoding="utf-8")
        logger.info("Loaded refusal prompt from %s", REFUSAL_PROMPT_PATH)
    return _refusal_prompt_template


# ---------------------------------------------------------------------------
# Groq client (lazy-loaded)
# ---------------------------------------------------------------------------
_groq_client = None


def _get_groq_client():
    """Lazy-load the Groq client."""
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY not set. Please set it in .env or environment variables."
            )
        _groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized with model: %s", GROQ_MODEL)
    return _groq_client


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def _format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a context string for the LLM prompt.

    Each chunk is formatted with its metadata for clear attribution.

    Args:
        chunks: List of retrieved chunk dicts.

    Returns:
        Formatted context string.
    """
    if not chunks:
        return "No relevant context found."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        scheme = chunk.get("scheme_name", "Unknown")
        source = chunk.get("source_url", "")
        chunk_type = chunk.get("chunk_type", "")
        text = chunk.get("text", "")

        context_parts.append(
            f"[Source {i}] ({scheme} — {chunk_type})\n"
            f"URL: {source}\n"
            f"{text}"
        )

    return "\n\n---\n\n".join(context_parts)


def _extract_last_updated(chunks: list[dict]) -> str:
    """
    Extract the most recent last_scraped_date from chunk metadata.

    Args:
        chunks: List of retrieved chunk dicts.

    Returns:
        The date string, or "Unknown" if not available.
    """
    dates = [
        chunk.get("last_scraped_date", "")
        for chunk in chunks
        if chunk.get("last_scraped_date")
    ]
    return dates[0] if dates else "Unknown"


# =========================================================================
# Public API
# =========================================================================

def generate_response(query: str, context_chunks: list[dict]) -> dict:
    """
    Generate a factual response using Groq LLM with rate limiting.

    Flow:
        1. Format the prompt (system prompt + context + query)
        2. Pre-flight rate check (estimate tokens, check can_request)
        3. Call Groq API
        4. Post-flight accounting (record actual tokens)
        5. Apply output guardrails

    Args:
        query: The user's factual query.
        context_chunks: Retrieved chunks from the vector store.

    Returns:
        A dict with:
            - status: "success" | "rate_limited" | "error"
            - answer: The generated response text
            - source: Citation URL
            - last_updated: Date string
            - query_type: "factual"
            - rate_limit_wait: Seconds to wait (if rate limited)
    """
    rate_limiter = get_rate_limiter()

    # --- Build the prompt ---
    system_prompt = _load_system_prompt()
    context_str = _format_context(context_chunks)
    last_updated = _extract_last_updated(context_chunks)

    formatted_prompt = system_prompt.replace(
        "{retrieved_chunks}", context_str
    ).replace(
        "{user_query}", query
    )

    # --- Pre-flight rate check ---
    estimated_tokens = rate_limiter.estimate_tokens(formatted_prompt) + MAX_TOKENS
    allowed, wait_seconds = rate_limiter.can_request(estimated_tokens)

    if not allowed:
        logger.warning(
            "Rate limited. Estimated tokens: %d. Wait: %.1fs",
            estimated_tokens, wait_seconds,
        )
        return {
            "status": "rate_limited",
            "answer": (
                f"I'm currently handling many requests. "
                f"Please try again in {int(wait_seconds)} seconds."
            ),
            "source": None,
            "last_updated": None,
            "query_type": "factual",
            "rate_limit_wait": wait_seconds,
        }

    # --- Call Groq API ---
    try:
        client = _get_groq_client()
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": formatted_prompt},
                {"role": "user", "content": query},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        # Extract response
        raw_answer = completion.choices[0].message.content or ""

        # --- Post-flight: record actual token usage ---
        tokens_used = getattr(completion.usage, "total_tokens", 0) if completion.usage else 0
        rate_limiter.record_request(tokens_used)

        logger.info(
            "Groq response received. Tokens used: %d (prompt: %d, completion: %d)",
            tokens_used,
            getattr(completion.usage, "prompt_tokens", 0) if completion.usage else 0,
            getattr(completion.usage, "completion_tokens", 0) if completion.usage else 0,
        )

    except Exception as e:
        logger.error("Groq API call failed: %s", e)
        return {
            "status": "error",
            "answer": "I'm having trouble generating a response right now. Please try again later.",
            "source": None,
            "last_updated": None,
            "query_type": "factual",
        }

    # --- Apply output guardrails ---
    guardrail_result = apply_output_guardrails(
        response=raw_answer,
        last_updated_date=last_updated,
    )

    if guardrail_result["blocked"]:
        return {
            "status": "error",
            "answer": guardrail_result["response"],
            "source": None,
            "last_updated": last_updated,
            "query_type": "factual",
        }

    # Log any guardrail warnings
    for warning in guardrail_result["warnings"]:
        logger.warning("Output guardrail warning: %s", warning)

    # Determine citation: prefer guardrail-extracted, fallback to first chunk
    citation = guardrail_result["citation_url"]
    if not citation and context_chunks:
        citation = context_chunks[0].get("source_url", "")

    return {
        "status": "success",
        "answer": guardrail_result["response"],
        "source": citation,
        "last_updated": last_updated,
        "query_type": "factual",
    }


def generate_refusal(query: str) -> dict:
    """
    Generate a template-based refusal for advisory queries.

    No Groq API call is made — conserves rate budget.

    Args:
        query: The user's advisory query.

    Returns:
        A dict with:
            - status: "refused"
            - answer: Polite refusal message
            - source: AMFI educational link
            - last_updated: None
            - query_type: "advisory"
    """
    logger.info("Generating template-based refusal for advisory query")

    return {
        "status": "refused",
        "answer": (
            "I can only provide factual information about mutual fund schemes, "
            "such as expense ratios, exit loads, and SIP details. "
            "For investment guidance, please visit "
            "https://www.amfiindia.com/investor-corner/knowledge-center.html"
        ),
        "source": "https://www.amfiindia.com/investor-corner/knowledge-center.html",
        "last_updated": None,
        "query_type": "advisory",
    }


def generate_pii_block(query: str) -> dict:
    """
    Generate a block response for queries containing PII.

    No Groq API call is made.

    Args:
        query: The user's query containing PII.

    Returns:
        A dict with:
            - status: "blocked"
            - answer: Security warning message
            - source: None
            - last_updated: None
            - query_type: "pii_detected"
    """
    logger.info("Generating PII block response")

    return {
        "status": "blocked",
        "answer": (
            "For your security, please do not share personal information "
            "like PAN, Aadhaar, or account numbers. "
            "I cannot process such data."
        ),
        "source": None,
        "last_updated": None,
        "query_type": "pii_detected",
    }
