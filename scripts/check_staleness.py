"""
Data staleness checker.

Reads the vector store metadata to determine when data was last ingested,
and exits with a non-zero code if the data is stale (older than a configurable
threshold). Used as a step in the GitHub Actions staleness-check workflow.

Exit codes:
    0 — Data is fresh (within threshold)
    1 — Data is stale (exceeds threshold), or no data found

Usage:
    python scripts/check_staleness.py                      # Default: 36h threshold
    python scripts/check_staleness.py --threshold-hours 24 # Custom threshold
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def check_staleness(threshold_hours: int = 36):
    """
    Check if vector store data is stale. Exits non-zero if stale.

    Args:
        threshold_hours: Maximum acceptable age of data in hours.
    """
    from src.ingestion.vectorstore import init_vectorstore

    print("=" * 60)
    print("DATA STALENESS CHECK")
    print(f"Threshold: {threshold_hours} hours")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Connect to vector store
    # ------------------------------------------------------------------
    try:
        collection = init_vectorstore()
    except Exception as e:
        print(f"\n❌ ERROR: Could not connect to vector store: {e}")
        sys.exit(1)

    count = collection.count()
    print(f"\n📊 Chunks in vector store: {count}")

    if count == 0:
        print("❌ STALE: No data found in vector store!")
        print("   The ingestion pipeline may not have been run yet.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Read metadata to find last ingestion date
    # ------------------------------------------------------------------
    try:
        results = collection.get(limit=1, include=["metadatas"])
    except Exception as e:
        print(f"❌ ERROR: Could not read metadata from vector store: {e}")
        sys.exit(1)

    if not results or not results.get("metadatas") or len(results["metadatas"]) == 0:
        print("❌ STALE: No metadata found in vector store!")
        sys.exit(1)

    last_date_str = results["metadatas"][0].get("last_scraped_date", "")

    if not last_date_str:
        print("❌ STALE: No 'last_scraped_date' field in chunk metadata!")
        print("   The ingestion pipeline may not be setting metadata correctly.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Calculate staleness
    # ------------------------------------------------------------------
    try:
        # Parse the date string — assume date-only format (YYYY-MM-DD)
        # and treat it as start-of-day UTC
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        hours_since = (now - last_date).total_seconds() / 3600

        print(f"📅 Last ingestion date: {last_date_str}")
        print(f"⏰ Current time (UTC):  {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏳ Hours since update:  {hours_since:.1f}h")

        if hours_since > threshold_hours:
            print(f"\n❌ STALE: Data is {hours_since:.1f}h old (threshold: {threshold_hours}h)")
            print("   The daily ingestion workflow may have failed or not triggered.")
            sys.exit(1)
        else:
            remaining = threshold_hours - hours_since
            print(f"\n✅ FRESH: Data is within the {threshold_hours}h threshold")
            print(f"   Time remaining before stale: {remaining:.1f}h")
            sys.exit(0)

    except ValueError:
        print(f"❌ ERROR: Could not parse date '{last_date_str}' (expected YYYY-MM-DD)")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check if vector store data is stale and exit non-zero if so."
    )
    parser.add_argument(
        "--threshold-hours",
        type=int,
        default=36,
        help="Maximum acceptable data age in hours (default: 36)",
    )
    args = parser.parse_args()
    check_staleness(args.threshold_hours)
