"""
Tests for the Groq Rate Limiter (src/pipeline/rate_limiter.py).

Tests cover:
    - RPM enforcement (sliding window)
    - TPM enforcement (sliding window)
    - RPD enforcement (daily counter)
    - TPD enforcement (daily counter)
    - Sliding window expiry
    - Daily reset logic
    - Token estimation
    - Status reporting
    - Thread safety
"""

import threading
import time
from unittest.mock import patch

import pytest

from src.pipeline.rate_limiter import GroqRateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def limiter():
    """Create a fresh GroqRateLimiter for each test."""
    return GroqRateLimiter()


@pytest.fixture
def small_limiter():
    """Create a rate limiter with small limits for easier testing."""
    rl = GroqRateLimiter()
    rl.RPM_LIMIT = 3
    rl.RPD_LIMIT = 10
    rl.TPM_LIMIT = 1_000
    rl.TPD_LIMIT = 5_000
    return rl


# =========================================================================
# Token Estimation
# =========================================================================

class TestEstimateTokens:
    """Tests for estimate_tokens() heuristic."""

    def test_empty_string(self, limiter):
        assert limiter.estimate_tokens("") == 0

    def test_short_text(self, limiter):
        # "hello" = 5 chars → 5 // 4 = 1
        assert limiter.estimate_tokens("hello") >= 1

    def test_typical_query(self, limiter):
        query = "What is the expense ratio of HDFC Large Cap Fund?"
        tokens = limiter.estimate_tokens(query)
        # ~50 chars → ~12 tokens
        assert 5 <= tokens <= 20

    def test_long_text(self, limiter):
        text = "word " * 400  # ~2000 chars
        tokens = limiter.estimate_tokens(text)
        # ~2000 chars → ~500 tokens
        assert 400 <= tokens <= 600

    def test_returns_int(self, limiter):
        result = limiter.estimate_tokens("test text")
        assert isinstance(result, int)


# =========================================================================
# RPM Enforcement
# =========================================================================

class TestRPMEnforcement:
    """Tests for requests-per-minute sliding window."""

    def test_allows_requests_within_limit(self, small_limiter):
        """Should allow requests up to RPM_LIMIT."""
        for _ in range(small_limiter.RPM_LIMIT):
            allowed, wait = small_limiter.can_request(100)
            assert allowed is True
            assert wait == 0.0
            small_limiter.record_request(100)

    def test_blocks_request_over_limit(self, small_limiter):
        """The RPM_LIMIT+1'th request should be blocked."""
        for _ in range(small_limiter.RPM_LIMIT):
            small_limiter.record_request(100)

        allowed, wait = small_limiter.can_request(100)
        assert allowed is False
        assert wait > 0.0

    def test_wait_time_is_positive(self, small_limiter):
        """Wait time should indicate when the oldest request expires."""
        for _ in range(small_limiter.RPM_LIMIT):
            small_limiter.record_request(100)

        _, wait = small_limiter.can_request(100)
        assert 0 < wait <= small_limiter.WINDOW_SECONDS


# =========================================================================
# TPM Enforcement
# =========================================================================

class TestTPMEnforcement:
    """Tests for tokens-per-minute sliding window."""

    def test_allows_tokens_within_limit(self, small_limiter):
        """Should allow requests if total tokens < TPM_LIMIT."""
        # Use 400 tokens, limit is 1000
        allowed, wait = small_limiter.can_request(400)
        assert allowed is True
        small_limiter.record_request(400)

        # 400 + 400 = 800 < 1000
        allowed, wait = small_limiter.can_request(400)
        assert allowed is True

    def test_blocks_when_exceeding_tpm(self, small_limiter):
        """Should block when estimated tokens would exceed TPM_LIMIT."""
        # Record 900 tokens (limit is 1000)
        small_limiter.record_request(900)

        # Requesting 200 more would exceed 1000
        allowed, wait = small_limiter.can_request(200)
        assert allowed is False
        assert wait > 0.0

    def test_exactly_at_limit(self, small_limiter):
        """Should block when at exactly the TPM limit."""
        small_limiter.record_request(1000)

        allowed, wait = small_limiter.can_request(1)
        assert allowed is False


# =========================================================================
# RPD Enforcement
# =========================================================================

class TestRPDEnforcement:
    """Tests for requests-per-day counter."""

    def test_allows_requests_within_daily_limit(self, small_limiter):
        """Should allow requests up to RPD_LIMIT."""
        for i in range(small_limiter.RPD_LIMIT):
            small_limiter.record_request(10)

        # The RPD_LIMIT + 1'th request should be blocked
        allowed, wait = small_limiter.can_request(10)
        assert allowed is False

    def test_daily_limit_wait_time(self, small_limiter):
        """Wait time for daily limit should be time until UTC midnight."""
        for _ in range(small_limiter.RPD_LIMIT):
            small_limiter.record_request(10)

        _, wait = small_limiter.can_request(10)
        # Should be positive (some time until midnight)
        assert wait > 0
        # Should not exceed 24 hours
        assert wait <= 86400


# =========================================================================
# TPD Enforcement
# =========================================================================

class TestTPDEnforcement:
    """Tests for tokens-per-day counter."""

    def test_blocks_when_exceeding_daily_tokens(self, small_limiter):
        """Should block when daily token total would exceed TPD_LIMIT."""
        small_limiter.TPM_LIMIT = 5000
        # Record 4900 tokens (limit is 5000). To avoid TPM (1000) we clear the window.
        small_limiter.record_request(4900)
        small_limiter._minute_window.clear()

        # Requesting 200 more would exceed 5000
        allowed, wait = small_limiter.can_request(200)
        assert allowed is False
        assert wait > 0

    def test_allows_within_daily_token_limit(self, small_limiter):
        """Should allow when within daily token budget."""
        small_limiter.TPM_LIMIT = 5000
        small_limiter.record_request(2000)
        small_limiter._minute_window.clear()

        allowed, wait = small_limiter.can_request(2000)
        assert allowed is True
        assert wait == 0.0


# =========================================================================
# Sliding Window Expiry
# =========================================================================

class TestSlidingWindowExpiry:
    """Tests for sliding window entry expiration."""

    def test_entries_expire_after_window(self, small_limiter):
        """Requests should become available after the window period."""
        # Override window to a very short duration for testing
        small_limiter.WINDOW_SECONDS = 0.1  # 100ms window

        # Fill the RPM limit
        for _ in range(small_limiter.RPM_LIMIT):
            small_limiter.record_request(100)

        # Should be blocked immediately
        allowed, _ = small_limiter.can_request(100)
        assert allowed is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be allowed again
        allowed, wait = small_limiter.can_request(100)
        assert allowed is True
        assert wait == 0.0

    def test_token_window_expiry(self, small_limiter):
        """Token counts should also expire with the sliding window."""
        small_limiter.WINDOW_SECONDS = 0.1

        # Use nearly all TPM budget
        small_limiter.record_request(900)

        # Should be blocked
        allowed, _ = small_limiter.can_request(200)
        assert allowed is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be allowed (minute tokens reset)
        allowed, wait = small_limiter.can_request(200)
        assert allowed is True


# =========================================================================
# Daily Reset
# =========================================================================

class TestDailyReset:
    """Tests for daily counter reset logic."""

    def test_counters_reset_on_date_change(self, small_limiter):
        """Daily counters should reset when UTC date changes."""
        # Fill daily limits
        for _ in range(small_limiter.RPD_LIMIT):
            small_limiter.record_request(100)
        
        # Clear the minute window so we aren't blocked by RPM limit
        small_limiter._minute_window.clear()

        # Should be blocked by RPD limit
        allowed, _ = small_limiter.can_request(100)
        assert allowed is False

        # Simulate date change by modifying _current_day
        small_limiter._current_day = "1970-01-01"

        # Should be allowed (daily counters reset)
        allowed, wait = small_limiter.can_request(100)
        assert allowed is True
        assert wait == 0.0

    def test_daily_token_count_resets(self, small_limiter):
        """Daily token count should reset on date change."""
        small_limiter.record_request(4900)
        
        # Clear the minute window so we aren't blocked by TPM limit
        small_limiter._minute_window.clear()

        # Blocked due to TPD
        allowed, _ = small_limiter.can_request(200)
        assert allowed is False

        # Simulate date change
        small_limiter._current_day = "1970-01-01"

        # Should be allowed
        allowed, _ = small_limiter.can_request(200)
        assert allowed is True


# =========================================================================
# Status Reporting
# =========================================================================

class TestGetStatus:
    """Tests for get_status() monitoring endpoint."""

    def test_initial_status(self, limiter):
        status = limiter.get_status()
        assert status["rpm"]["used"] == 0
        assert status["rpm"]["limit"] == 30
        assert status["rpm"]["remaining"] == 30
        assert status["rpd"]["used"] == 0
        assert status["rpd"]["limit"] == 1000
        assert status["tpm"]["used"] == 0
        assert status["tpm"]["limit"] == 12000
        assert status["tpd"]["used"] == 0
        assert status["tpd"]["limit"] == 100000
        assert "current_day_utc" in status

    def test_status_after_requests(self, limiter):
        limiter.record_request(500)
        limiter.record_request(300)

        status = limiter.get_status()
        assert status["rpm"]["used"] == 2
        assert status["rpd"]["used"] == 2
        assert status["tpm"]["used"] == 800
        assert status["tpd"]["used"] == 800

    def test_status_remaining_calculation(self, limiter):
        limiter.record_request(1000)

        status = limiter.get_status()
        assert status["rpm"]["remaining"] == 29
        assert status["rpd"]["remaining"] == 999
        assert status["tpm"]["remaining"] == 11000
        assert status["tpd"]["remaining"] == 99000


# =========================================================================
# Thread Safety
# =========================================================================

class TestThreadSafety:
    """Tests for thread-safe operation."""

    def test_concurrent_record_requests(self, small_limiter):
        """Multiple threads recording requests shouldn't corrupt counters."""
        small_limiter.RPD_LIMIT = 1000  # raise limit to avoid blocking
        small_limiter.TPD_LIMIT = 100000
        small_limiter.RPM_LIMIT = 1000
        small_limiter.TPM_LIMIT = 100000

        errors = []
        num_threads = 10
        requests_per_thread = 20

        def worker():
            try:
                for _ in range(requests_per_thread):
                    small_limiter.record_request(10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        status = small_limiter.get_status()
        expected_requests = num_threads * requests_per_thread
        expected_tokens = expected_requests * 10

        assert status["rpd"]["used"] == expected_requests
        assert status["tpd"]["used"] == expected_tokens

    def test_concurrent_can_request(self, small_limiter):
        """Multiple threads checking can_request shouldn't crash."""
        errors = []

        def worker():
            try:
                for _ in range(50):
                    small_limiter.can_request(100)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
