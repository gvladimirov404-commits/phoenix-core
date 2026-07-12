"""Unit tests for phoenix_core.guard.rate_limiter.RateLimiter."""
import pytest

from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.utils.exceptions import RateLimitExceededError


class TestCheck:
    def test_allows_requests_up_to_the_limit(self) -> None:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        limiter.check(1)
        limiter.check(1)
        limiter.check(1)  # 3rd request within limit, should not raise

    def test_raises_once_limit_exceeded(self) -> None:
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check(1)
        limiter.check(1)
        with pytest.raises(RateLimitExceededError):
            limiter.check(1)

    def test_different_users_have_independent_limits(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check(1)
        limiter.check(2)  # different user, independent budget, should not raise

    def test_window_resets_after_expiry(self, monkeypatch) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=10)
        fake_time = [1000.0]
        monkeypatch.setattr("phoenix_core.guard.rate_limiter.time.monotonic", lambda: fake_time[0])

        limiter.check(1)
        with pytest.raises(RateLimitExceededError):
            limiter.check(1)

        fake_time[0] += 11  # past the window
        limiter.check(1)  # should succeed again


class TestActiveEntries:
    def test_counts_only_unexpired_windows(self, monkeypatch) -> None:
        limiter = RateLimiter(max_requests=5, window_seconds=10)
        fake_time = [0.0]
        monkeypatch.setattr("phoenix_core.guard.rate_limiter.time.monotonic", lambda: fake_time[0])

        limiter.check(1)
        limiter.check(2)
        assert limiter.active_entries == 2

        fake_time[0] += 20
        assert limiter.active_entries == 0


class TestConstruction:
    def test_invalid_max_requests_rejected(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(max_requests=0)

    def test_invalid_window_rejected(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(window_seconds=0)


class TestHealthCheck:
    async def test_reports_configured_limits(self) -> None:
        limiter = RateLimiter(max_requests=7, window_seconds=42)
        limiter.check(1)

        health = await limiter.health_check()

        assert health["status"] == "healthy"
        assert health["max_requests"] == 7
        assert health["window_seconds"] == 42
        assert health["active_entries"] == 1
