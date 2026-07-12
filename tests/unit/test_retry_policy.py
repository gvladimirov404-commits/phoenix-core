"""Unit tests for phoenix_core.guard.retry.RetryPolicy."""
import pytest

from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderTimeoutError,
    ConfigurationError,
    ValidationError,
)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Never actually sleep in tests — replace backoff delay with a no-op."""
    async def fake_sleep(seconds):
        return None
    monkeypatch.setattr("phoenix_core.guard.retry.asyncio.sleep", fake_sleep)


def make_flaky_call(fail_times: int, exception: Exception, result: str = "ok"):
    calls = {"count": 0}

    async def call():
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise exception
        return result

    return call, calls


class TestSuccessPath:
    async def test_succeeds_on_first_try_without_retry(self) -> None:
        policy = RetryPolicy(max_retries=2)

        async def call():
            return "ok"

        result = await policy.run(call)
        assert result == "ok"

    async def test_succeeds_after_retryable_failures_within_budget(self) -> None:
        policy = RetryPolicy(max_retries=3)
        call, calls = make_flaky_call(fail_times=2, exception=AIProviderTimeoutError("timeout"))

        result = await policy.run(call)

        assert result == "ok"
        assert calls["count"] == 3  # 2 failures + 1 success


class TestRetryExhaustion:
    async def test_raises_after_exhausting_retries(self) -> None:
        policy = RetryPolicy(max_retries=2)
        call, calls = make_flaky_call(fail_times=99, exception=AIProviderConnectionError("boom"))

        with pytest.raises(AIProviderConnectionError):
            await policy.run(call)

        assert calls["count"] == 3  # 1 initial + 2 retries

    async def test_zero_retries_means_single_attempt(self) -> None:
        policy = RetryPolicy(max_retries=0)
        call, calls = make_flaky_call(fail_times=1, exception=AIProviderTimeoutError("timeout"))

        with pytest.raises(AIProviderTimeoutError):
            await policy.run(call)

        assert calls["count"] == 1


class TestNonRetryableExceptions:
    async def test_configuration_error_propagates_immediately(self) -> None:
        policy = RetryPolicy(max_retries=3)
        call, calls = make_flaky_call(fail_times=99, exception=ConfigurationError("bad config"))

        with pytest.raises(ConfigurationError):
            await policy.run(call)

        assert calls["count"] == 1  # no retry attempted

    async def test_validation_error_propagates_immediately(self) -> None:
        policy = RetryPolicy(max_retries=3)
        call, calls = make_flaky_call(fail_times=99, exception=ValidationError("bad input"))

        with pytest.raises(ValidationError):
            await policy.run(call)

        assert calls["count"] == 1

    async def test_generic_ai_provider_error_not_retried_by_default(self) -> None:
        """AIProviderError is also used for auth failures — not retried (see module docstring)."""
        policy = RetryPolicy(max_retries=3)
        call, calls = make_flaky_call(fail_times=99, exception=AIProviderError("auth failed"))

        with pytest.raises(AIProviderError):
            await policy.run(call)

        assert calls["count"] == 1


class TestConstruction:
    def test_negative_max_retries_rejected(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_retries=-1)


class TestHealthCheck:
    async def test_reports_configured_values(self) -> None:
        policy = RetryPolicy(max_retries=4, base_delay=1.0, max_delay=10.0)
        health = await policy.health_check()
        assert health == {"max_retries": 4, "base_delay_seconds": 1.0, "max_delay_seconds": 10.0}
