"""
FastAPI application for the Mutual Fund FAQ Assistant.

Endpoints:
    POST /ask              — Query the mutual fund FAQ pipeline
    GET  /health           — Health check
    GET  /rate-limit-status — Current Groq rate limiter usage

The full pipeline flow for POST /ask:
    1. Input guardrails (PII check, length cap, injection strip)
    2. Classify query (factual / advisory / pii_detected)
    3. Route:
        - advisory     → generate_refusal()       (no Groq call)
        - pii_detected → generate_pii_block()     (no Groq call)
        - factual      → retrieve() → generate_response() (rate-limited Groq call)
    4. Return structured QueryResponse
"""

from __future__ import annotations

import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.models import (
    HealthResponse,
    IngestionStatusResponse,
    QueryRequest,
    QueryResponse,
    RateLimitStatusResponse,
)
from src.pipeline.guardrails import apply_input_guardrails
from src.pipeline.query_classifier import classify
from src.pipeline.generator import (
    generate_pii_block,
    generate_refusal,
    generate_response,
)
from src.pipeline.rate_limiter import get_rate_limiter
from src.pipeline.retriever import retrieve

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Mutual Fund FAQ Assistant",
    description=(
        "A RAG-based FAQ assistant for HDFC Mutual Fund schemes. "
        "Ask factual questions about expense ratios, exit loads, SIP details, and more."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """
    Health check endpoint.

    Returns the service status, configured LLM model, and vector store readiness.
    """
    # Check if the vector store directory exists
    vector_store_path = os.getenv("VECTOR_STORE_PATH", "./vectorstore")
    vs_ready = os.path.isdir(vector_store_path)

    return HealthResponse(
        status="healthy",
        model=GROQ_MODEL,
        vector_store_ready=vs_ready,
    )


@app.get("/rate-limit-status", response_model=RateLimitStatusResponse, tags=["System"])
async def rate_limit_status():
    """
    Return current Groq rate limiter usage across all 4 limit dimensions.

    Useful for monitoring how much of the free-tier budget has been consumed.
    """
    limiter = get_rate_limiter()
    status = limiter.get_status()
    return RateLimitStatusResponse(**status)


@app.post("/ask", response_model=QueryResponse, tags=["Query"])
async def ask(request: QueryRequest):
    """
    Main query endpoint — runs the full FAQ pipeline.

    Flow:
        1. Input guardrails (PII, length, injection)
        2. Classify query
        3. Route to appropriate handler
        4. Return structured response
    """
    start_time = time.time()
    query = request.query.strip()

    logger.info("Received query: '%s'", query[:80])

    # ------------------------------------------------------------------
    # Step 1: Input guardrails
    # ------------------------------------------------------------------
    sanitized_query, guardrail_error = apply_input_guardrails(query)

    if guardrail_error:
        logger.warning("Input guardrail blocked query: %s", guardrail_error)
        return QueryResponse(
            status="blocked",
            answer=guardrail_error,
            source=None,
            last_updated=None,
            query_type="pii_detected",
        )

    # ------------------------------------------------------------------
    # Step 2: Classify query
    # ------------------------------------------------------------------
    query_type = classify(sanitized_query)
    logger.info("Query classified as: %s", query_type)

    # ------------------------------------------------------------------
    # Step 3: Route to handler
    # ------------------------------------------------------------------
    if query_type == "advisory":
        result = generate_refusal(sanitized_query)

    elif query_type == "pii_detected":
        result = generate_pii_block(sanitized_query)

    else:
        # Factual query — full RAG pipeline
        try:
            chunks = retrieve(sanitized_query, top_k=3)
            logger.info("Retrieved %d chunks", len(chunks))

            if not chunks:
                result = {
                    "status": "success",
                    "answer": (
                        "I don't have this information in my sources. "
                        "Please check https://groww.in/mutual-funds for the latest details."
                    ),
                    "source": "https://groww.in/mutual-funds",
                    "last_updated": None,
                    "query_type": "factual",
                }
            else:
                result = generate_response(sanitized_query, chunks)

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)
            result = {
                "status": "error",
                "answer": "I'm having trouble processing your request right now. Please try again later.",
                "source": None,
                "last_updated": None,
                "query_type": "factual",
            }

    # ------------------------------------------------------------------
    # Step 4: Return response
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time
    logger.info(
        "Query processed in %.2fs — status: %s, type: %s",
        elapsed, result.get("status"), result.get("query_type"),
    )

    return QueryResponse(
        status=result.get("status", "error"),
        answer=result.get("answer", ""),
        source=result.get("source"),
        last_updated=result.get("last_updated"),
        query_type=result.get("query_type", query_type),
    )


# ---------------------------------------------------------------------------
# Ingestion Status — Data freshness reporting
# ---------------------------------------------------------------------------


@app.get("/ingestion/status", response_model=IngestionStatusResponse, tags=["System"])
async def ingestion_status():
    """
    Returns the freshness status of the indexed data.

    Reports the current chunk count, last scraped date, and scheduler info.
    This is a lightweight read-only endpoint — no in-process scheduler needed.
    """
    try:
        from src.ingestion.vectorstore import init_vectorstore

        collection = init_vectorstore()
        chunk_count = collection.count()

        # Read metadata from a sample chunk to get last_scraped_date
        last_date = "unknown"
        if chunk_count > 0:
            results = collection.get(limit=1, include=["metadatas"])
            if (
                results
                and results.get("metadatas")
                and len(results["metadatas"]) > 0
            ):
                last_date = results["metadatas"][0].get(
                    "last_scraped_date", "unknown"
                )
    except Exception as e:
        logger.error("Failed to read ingestion status: %s", e)
        chunk_count = 0
        last_date = "error"

    return IngestionStatusResponse(
        chunk_count=chunk_count,
        last_scraped_date=last_date,
        scheduler="GitHub Actions (daily at 05:00 UTC / 10:30 AM IST)",
        staleness_check="GitHub Actions (every 6 hours)",
    )


# ---------------------------------------------------------------------------
# Static Files — Serve the frontend UI
# ---------------------------------------------------------------------------
# IMPORTANT: This MUST be the last mount — it catches all unmatched routes.
_ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
if os.path.isdir(_ui_dir):
    app.mount("/", StaticFiles(directory=_ui_dir, html=True), name="ui")
    logger.info("Serving frontend UI from %s", _ui_dir)

