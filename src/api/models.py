"""
Pydantic request/response models for the Mutual Fund FAQ Assistant API.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for the /ask endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The user's mutual fund question (max 500 characters).",
        examples=["What is the expense ratio of HDFC Large Cap Fund?"],
    )


class QueryResponse(BaseModel):
    """Response body from the /ask endpoint."""

    status: str = Field(
        ...,
        description=(
            "Outcome of the query. One of: "
            "'success', 'refused', 'blocked', 'rate_limited', 'error'."
        ),
    )
    answer: str = Field(
        ...,
        description="The assistant's response text.",
    )
    source: Optional[str] = Field(
        None,
        description="Citation URL (Groww or AMFI link), if applicable.",
    )
    last_updated: Optional[str] = Field(
        None,
        description="Date the source data was last scraped, if applicable.",
    )
    query_type: str = Field(
        ...,
        description=(
            "Classification of the query. One of: "
            "'factual', 'advisory', 'pii_detected'."
        ),
    )


class HealthResponse(BaseModel):
    """Response body for the /health endpoint."""

    status: str = "healthy"
    model: str = ""
    vector_store_ready: bool = False


class RateLimitStatusResponse(BaseModel):
    """Response body for the /rate-limit-status endpoint."""

    rpm: dict = Field(default_factory=dict, description="Requests per minute usage")
    rpd: dict = Field(default_factory=dict, description="Requests per day usage")
    tpm: dict = Field(default_factory=dict, description="Tokens per minute usage")
    tpd: dict = Field(default_factory=dict, description="Tokens per day usage")
    current_day_utc: str = ""


class IngestionStatusResponse(BaseModel):
    """Response body for the /ingestion/status endpoint."""

    chunk_count: int = Field(
        ...,
        description="Number of chunks currently indexed in the vector store.",
    )
    last_scraped_date: str = Field(
        ...,
        description="Date when the data was last scraped (YYYY-MM-DD or 'unknown').",
    )
    scheduler: str = Field(
        ...,
        description="Description of the automated scheduling mechanism.",
    )
    staleness_check: str = Field(
        ...,
        description="Description of the staleness monitoring mechanism.",
    )

