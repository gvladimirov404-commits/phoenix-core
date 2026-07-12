"""Unit tests for phoenix_core.guard.guard.AIGuard."""
import pytest

from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.guard.guard import AIGuard
from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.guard.sanitizer import OutputSanitizer
from phoenix_core.utils.exceptions import (
    AIProviderTimeoutError,
    ContextTooLargeError,
    PromptTooLargeError,
    RateLimitExceededError,
)


def make_guard(max_requests=10, window=60, max_prompt=4000, max_context=12000, max_retries=2) -> AIGuard:
    return AIGuard(
        rate_limiter=RateLimiter(max_requests=max_requests, window_seconds=window),
        cost_guard=CostGuard(max_prompt_chars=max_prompt, max_context_chars=max_context),
        retry_policy=RetryPolicy(max_retries=max_retries),
        sanitizer=OutputSanitizer(),
    )


class TestGuardRequest:
    def test_passes_when_within_all_limits(self) -> None:
        guard = make_guard()
        guard.guard_request(1, "hello", [{"role": "user", "content": "hello"}])

    def test_raises_rate_limit_exceeded(self) -> None:
        guard = make_guard(max_requests=1)
        guard.guard_request(1, "hi", [{"role": "user", "content": "hi"}])
        with pytest.raises(RateLimitExceededError):
            guard.guard_request(1, "hi again", [{"role": "user", "content": "hi again"}])

    def test_raises_prompt_too_large(self) -> None:
        guard = make_guard(max_prompt=5)
        with pytest.raises(PromptTooLargeError):
            guard.guard_request(1, "this prompt is too long", [{"role": "user", "content": "x"}])

    def test_raises_context_too_large(self) -> None:
        guard = make_guard(max_context=5)
        with pytest.raises(ContextTooLargeError):
            guard.guard_request(1, "hi", [{"role": "user", "content": "0123456789"}])

    def test_rate_limit_checked_before_cost_guard(self) -> None:
        """Rate limit is exhausted first; a second call should fail on rate limit,
        not be allowed through to hit the (also failing) cost check."""
        guard = make_guard(max_requests=1, max_prompt=1)
        guard.guard_request(1, "x", [{"role": "user", "content": "x"}])
        with pytest.raises(RateLimitExceededError):
            guard.guard_request(1, "this is too long for the prompt limit", [{"role": "user", "content": "x"}])


class TestCallProvider:
    async def test_delegates_to_retry_policy(self) -> None:
        guard = make_guard(max_retries=2)

        async def call():
            return "provider-result"

        result = await guard.call_provider(call)
        assert result == "provider-result"

    async def test_retries_transient_errors(self, monkeypatch) -> None:
        async def fake_sleep(seconds):
            return None
        monkeypatch.setattr("phoenix_core.guard.retry.asyncio.sleep", fake_sleep)

        guard = make_guard(max_retries=2)
        calls = {"count": 0}

        async def call():
            calls["count"] += 1
            if calls["count"] < 2:
                raise AIProviderTimeoutError("timeout")
            return "ok"

        result = await guard.call_provider(call)
        assert result == "ok"
        assert calls["count"] == 2


class TestSanitizeOutput:
    def test_delegates_to_sanitizer(self) -> None:
        guard = make_guard()
        assert guard.sanitize_output("hello") == "hello"


class TestHealthCheck:
    async def test_aggregates_all_components(self) -> None:
        guard = make_guard(max_requests=5, window=30, max_prompt=100, max_context=200, max_retries=1)
        health = await guard.health_check()

        assert health["status"] == "healthy"
        assert health["rate_limiter"]["max_requests"] == 5
        assert health["rate_limiter"]["window_seconds"] == 30
        assert health["cost_guard"]["max_prompt_chars"] == 100
        assert health["cost_guard"]["max_context_chars"] == 200
        assert health["retry_policy"]["max_retries"] == 1
        assert "max_length" in health["sanitizer"]
