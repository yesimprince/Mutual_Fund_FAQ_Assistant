"""
Post-ingestion validation script.

Validates the integrity and freshness of the vector store after a full
ingestion run. Used as a step in the GitHub Actions daily-ingestion workflow.

Exit codes:
    0 — Validation passed (all checks OK)
    1 — Validation failed (chunk count out of range, or critical error)

Usage:
    python scripts/validate_ingestion.py
"""

import sys
import os
import logging
from datetime import date

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Expected chunk count bounds (5 schemes × ~11 chunks each = ~55)
MIN_EXPECTED_CHUNKS = 40
MAX_EXPECTED_CHUNKS = 80


def validate():
    """
    Post-ingestion validation — exits non-zero on failure.

    Checks:
        1. Vector store is accessible and non-empty
        2. Chunk count is within expected range (~40–80)
        3. Data freshness — last_scraped_date should be today
    """
    from src.ingestion.vectorstore import init_vectorstore

    print("=" * 60)
    print("POST-INGESTION VALIDATION")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Check 1: Vector store accessibility
    # ------------------------------------------------------------------
    try:
        collection = init_vectorstore()
    except Exception as e:
        print(f"❌ FAIL: Could not connect to vector store: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Check 2: Chunk count
    # ------------------------------------------------------------------
    count = collection.count()
    print(f"\n📊 Chunk count: {count}")

    if count == 0:
        print("❌ FAIL: Vector store is empty — no chunks found!")
        sys.exit(1)

    if count < MIN_EXPECTED_CHUNKS:
        print(
            f"❌ FAIL: Chunk count too low — expected ≥{MIN_EXPECTED_CHUNKS}, "
            f"got {count}. Possible scraping or parsing failure."
        )
        sys.exit(1)

    if count > MAX_EXPECTED_CHUNKS:
        print(
            f"❌ FAIL: Chunk count too high — expected ≤{MAX_EXPECTED_CHUNKS}, "
            f"got {count}. Possible duplicate ingestion or chunking error."
        )
        sys.exit(1)

    print(f"✅ Chunk count is within expected range ({MIN_EXPECTED_CHUNKS}–{MAX_EXPECTED_CHUNKS})")

    # ------------------------------------------------------------------
    # Check 3: Data freshness
    # ------------------------------------------------------------------
    try:
        results = collection.get(limit=1, include=["metadatas"])
    except Exception as e:
        print(f"⚠️  WARNING: Could not read metadata: {e}")
        print("✅ Validation PASSED (with warnings)")
        sys.exit(0)

    if results and results.get("metadatas") and len(results["metadatas"]) > 0:
        metadata = results["metadatas"][0]
        last_date = metadata.get("last_scraped_date", "unknown")
        today = date.today().isoformat()

        print(f"📅 Latest scraped date: {last_date}")
        print(f"📅 Today's date:        {today}")

        if last_date == today:
            print("✅ Data is from today — freshness check passed")
        elif last_date == "unknown":
            print("⚠️  WARNING: No last_scraped_date in metadata — cannot verify freshness")
        else:
            print(
                f"⚠️  WARNING: Data date ({last_date}) ≠ today ({today}). "
                "Data may be from a previous ingestion run."
            )

        # Report scheme coverage
        scheme_name = metadata.get("scheme_name", "unknown")
        chunk_type = metadata.get("chunk_type", "unknown")
        print(f"📋 Sample chunk — scheme: {scheme_name}, type: {chunk_type}")
    else:
        print("⚠️  WARNING: No metadata found on chunks")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("✅ VALIDATION PASSED")
    print(f"   Chunks indexed: {count}")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    validate()
