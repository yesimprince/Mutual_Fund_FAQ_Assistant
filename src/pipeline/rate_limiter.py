"""
Groq API Rate Limiter for the Mutual Fund FAQ Assistant.

Enforces the free-tier limits for llama-3.3-70b-versatile:
    - Requests per minute (RPM): 30
    - Requests per day (RPD): 1,000
    - Tokens per minute (TPM): 12,000
    - Tokens per day (TPD): 100,000

Implementation:
    - Sliding-window counters for per-minute limits (RPM, TPM)
    - Daily counters for per-day limits (RPD, TPD) — reset at UTC midnight
    - Thread-safe via threading.Lock
    - Pre-flight check (can_request) + post-flight accounting (record_request)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class GroqRateLimiter:
    """
    Thread-safe rate limiter for Groq API calls.

    Enforces 4 limits using two strategies:
        - Sliding window (60s) for RPM and TPM
        - Daily counter (UTC midnight reset) for RPD and TPD
    """

    # Groq free-tier limits for llama-3.3-70b-versatile
    RPM_LIMIT = 30          # requests per minute
    RPD_LIMIT = 1_000       # requests per day
    TPM_LIMIT = 12_000      # tokens per minute
    TPD_LIMIT = 100_000     # tokens per day

    WINDOW_SECONDS = 60.0   # sliding window size

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Sliding window: deque of (timestamp, token_count) tuples
        self._minute_window: deque[tuple[float, int]] = deque()

        # Daily counters
        self._daily_request_count = 0
        self._daily_token_count = 0
        self._current_day: str = self._utc_today()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_request(self, estimated_tokens: int) -> tuple[bool, float]:
        """
        Pre-flight check: can we make a Groq API call right now?

        Args:
            estimated_tokens: Estimated total tokens for the request
                              (prompt + expected completion).

        Returns:
            A tuple of (allowed, wait_seconds).
            - If allowed is True, wait_seconds is 0.0.
            - If allowed is False, wait_seconds is the estimated time to wait
              before retrying.
        """
        with self._lock:
            self._maybe_reset_daily()
            self._evict_expired()

            # --- Check daily limits first (longer wait) ---
            if self._daily_request_count >= self.RPD_LIMIT:
                wait = self._seconds_until_midnight()
                logger.warning(
                    "RPD limit reached (%d/%d). Wait %.0fs until UTC midnight.",
                    self._daily_request_count, self.RPD_LIMIT, wait,
                )
                return False, wait

            if self._daily_token_count + estimated_tokens > self.TPD_LIMIT:
                wait = self._seconds_until_midnight()
                logger.warning(
                    "TPD limit would be exceeded (%d + %d > %d). Wait %.0fs.",
                    self._daily_token_count, estimated_tokens, self.TPD_LIMIT, wait,
                )
                return False, wait

            # --- Check per-minute limits (shorter wait) ---
            minute_requests = len(self._minute_window)
            minute_tokens = sum(t for _, t in self._minute_window)

            if minute_requests >= self.RPM_LIMIT:
                wait = self._wait_for_window_slot()
                logger.warning(
                    "RPM limit reached (%d/%d). Wait %.1fs.",
                    minute_requests, self.RPM_LIMIT, wait,
                )
                return False, wait

            if minute_tokens + estimated_tokens > self.TPM_LIMIT:
                wait = self._wait_for_window_slot()
                logger.warning(
                    "TPM limit would be exceeded (%d + %d > %d). Wait %.1fs.",
                    minute_tokens, estimated_tokens, self.TPM_LIMIT, wait,
                )
                return False, wait

            return True, 0.0

    def record_request(self, tokens_used: int) -> None:
        """
        Post-flight: record actual token usage after a successful Groq API call.

        Args:
            tokens_used: Actual total tokens consumed (from Groq response
                         usage.total_tokens).
        """
        now = time.monotonic()
        with self._lock:
            self._maybe_reset_daily()

            # Add to sliding window
            self._minute_window.append((now, tokens_used))

            # Increment daily counters
            self._daily_request_count += 1
            self._daily_token_count += tokens_used

            logger.info(
                "Recorded request: %d tokens. "
                "Minute: %d/%d RPM, %d/%d TPM. "
                "Daily: %d/%d RPD, %d/%d TPD.",
                tokens_used,
                len(self._minute_window), self.RPM_LIMIT,
                sum(t for _, t in self._minute_window), self.TPM_LIMIT,
                self._daily_request_count, self.RPD_LIMIT,
                self._daily_token_count, self.TPD_LIMIT,
            )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough token estimate using the ~4 chars per token heuristic.

        This is a conservative estimate. Actual tokenization varies by model,
        but for pre-flight rate checks, this is sufficient.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count (always >= 1 for non-empty text).
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    def get_status(self) -> dict:
        """
        Return current usage stats for monitoring and debugging.

        Returns:
            A dict with current usage across all 4 limit dimensions.
        """
        with self._lock:
            self._maybe_reset_daily()
            self._evict_expired()

            minute_requests = len(self._minute_window)
            minute_tokens = sum(t for _, t in self._minute_window)

            return {
                "rpm": {"used": minute_requests, "limit": self.RPM_LIMIT,
                        "remaining": self.RPM_LIMIT - minute_requests},
                "rpd": {"used": self._daily_request_count, "limit": self.RPD_LIMIT,
                        "remaining": self.RPD_LIMIT - self._daily_request_count},
                "tpm": {"used": minute_tokens, "limit": self.TPM_LIMIT,
                        "remaining": self.TPM_LIMIT - minute_tokens},
                "tpd": {"used": self._daily_token_count, "limit": self.TPD_LIMIT,
                        "remaining": self.TPD_LIMIT - self._daily_token_count},
                "current_day_utc": self._current_day,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        """Remove entries older than WINDOW_SECONDS from the sliding window."""
        cutoff = time.monotonic() - self.WINDOW_SECONDS
        while self._minute_window and self._minute_window[0][0] < cutoff:
            self._minute_window.popleft()

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters if the UTC date has changed."""
        today = self._utc_today()
        if today != self._current_day:
            logger.info(
                "Daily reset: %s -> %s. Previous day: %d requests, %d tokens.",
                self._current_day, today,
                self._daily_request_count, self._daily_token_count,
            )
            self._current_day = today
            self._daily_request_count = 0
            self._daily_token_count = 0

    def _wait_for_window_slot(self) -> float:
        """Calculate seconds until the oldest window entry expires."""
        if not self._minute_window:
            return 0.0
        oldest_ts = self._minute_window[0][0]
        expires_at = oldest_ts + self.WINDOW_SECONDS
        wait = expires_at - time.monotonic()
        return max(0.0, wait)

    @staticmethod
    def _utc_today() -> str:
        """Return today's date string in UTC (YYYY-MM-DD)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _seconds_until_midnight() -> float:
        """Calculate seconds until the next UTC midnight."""
        now = datetime.now(timezone.utc)
        midnight = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Move to next day
        from datetime import timedelta
        next_midnight = midnight + timedelta(days=1)
        delta = next_midnight - now
        return delta.total_seconds()


# ---------------------------------------------------------------------------
# Module-level singleton (shared across the application)
# ---------------------------------------------------------------------------
_rate_limiter: GroqRateLimiter | None = None


def get_rate_limiter() -> GroqRateLimiter:
    """
    Get or create the singleton GroqRateLimiter instance.

    Returns:
        The shared GroqRateLimiter instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GroqRateLimiter()
    return _rate_limiter
