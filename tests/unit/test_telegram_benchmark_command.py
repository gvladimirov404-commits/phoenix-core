"""Unit tests for cmd_benchmark (Benchmark roadmap item)."""
import pytest

from phoenix_core.ai.router import AIRouter
from phoenix_core.core.container import Container
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext

from .conftest import MockAIProvider

pytestmark = pytest.mark.asyncio


def make_context(user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=user_id, command="test")


def make_router() -> AIRouter:
    return AIRouter(providers=[], default_provider="mock")


class TestCmdBenchmark:
    async def test_missing_ai_router_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_benchmark([], make_context(), container)
        assert "не е наличен" in result

    async def test_no_providers_registered_returns_friendly_message(self) -> None:
        container = Container()
        container.register("ai_router", make_router())
        result = await commands.cmd_benchmark([], make_context(), container)
        assert "не е наличен" in result

    async def test_returns_success_rate_and_latency_for_provider(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        result = await commands.cmd_benchmark([], make_context(), container)

        assert "mock" in result
        assert "Успеваемост" in result
        assert "100%" in result
        assert "Средно време за отговор" in result

    async def test_shows_errors_for_failing_provider(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(should_fail=RuntimeError("boom")))
        container.register("ai_router", router)

        result = await commands.cmd_benchmark([], make_context(), container)

        assert "0%" in result
        assert "Грешки" in result
        assert "RuntimeError" in result


class TestCmdBenchmarkAIGuard:
    """Task 032: /benchmark must be protected by the same AI Guard used
    by /ask, /explain, /consensus, /copilot, and /research —
    guard_request() must run before PhoenixBenchmark.run() is ever
    called, so a rejected request never reaches any provider."""

    def _make_guard(self, rate_limiter=None, cost_guard=None):
        from phoenix_core.guard.guard import AIGuard
        from phoenix_core.guard.retry import RetryPolicy
        from phoenix_core.guard.sanitizer import OutputSanitizer

        return AIGuard(
            rate_limiter=rate_limiter or _AlwaysAllowRateLimiter(),
            cost_guard=cost_guard or _AlwaysAllowCostGuard(),
            retry_policy=RetryPolicy(max_retries=0),
            sanitizer=OutputSanitizer(),
        )

    async def test_guard_request_is_called_before_benchmark_run(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        calls = []

        class RecordingRateLimiter:
            def check(self, user_id):
                calls.append("guard_request")

        guard = self._make_guard(rate_limiter=RecordingRateLimiter())
        container.register("ai_guard", guard)

        import phoenix_core.ai.benchmark as benchmark_module
        original_run = benchmark_module.PhoenixBenchmark.run

        async def recording_run(self):
            calls.append("benchmark_run")
            return await original_run(self)

        benchmark_module.PhoenixBenchmark.run = recording_run
        try:
            await commands.cmd_benchmark([], make_context(), container)
        finally:
            benchmark_module.PhoenixBenchmark.run = original_run

        assert calls == ["guard_request", "benchmark_run"]

    async def test_rejected_guard_prevents_benchmark_run(self) -> None:
        from phoenix_core.utils.exceptions import RateLimitExceededError

        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        class RejectingRateLimiter:
            def check(self, user_id):
                raise RateLimitExceededError("rate limit hit")

        guard = self._make_guard(rate_limiter=RejectingRateLimiter())
        container.register("ai_guard", guard)

        import phoenix_core.ai.benchmark as benchmark_module
        original_run = benchmark_module.PhoenixBenchmark.run

        async def asserting_run(self):
            asserting_run.called = True
            raise AssertionError("PhoenixBenchmark.run must not be called for a rejected guard")
        asserting_run.called = False

        benchmark_module.PhoenixBenchmark.run = asserting_run
        try:
            result = await commands.cmd_benchmark([], make_context(), container)
        finally:
            benchmark_module.PhoenixBenchmark.run = original_run

        assert result  # a friendly rejection message was returned, not an empty/raised result
        assert asserting_run.called is False

    async def test_authorized_request_reaches_benchmark_run(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        guard = self._make_guard()
        container.register("ai_guard", guard)

        result = await commands.cmd_benchmark([], make_context(), container)

        assert "mock" in result
        assert "Успеваемост" in result

    async def test_existing_no_guard_behavior_is_preserved(self) -> None:
        """No ai_guard registered at all — /benchmark must still work
        exactly as before Task 032 (ai_guard is optional, same as every
        other AI command)."""
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        result = await commands.cmd_benchmark([], make_context(), container)

        assert "mock" in result
        assert "Успеваемост" in result


class _AlwaysAllowRateLimiter:
    def check(self, user_id):
        pass


class _AlwaysAllowCostGuard:
    def check_prompt(self, prompt):
        pass

    def check_context(self, messages):
        pass
