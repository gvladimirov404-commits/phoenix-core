"""Unit tests for cmd_consensus (Roadmap item 5 / TASK-021 Part 9)."""
from types import SimpleNamespace

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


class TestCmdConsensus:
    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        result = await commands.cmd_consensus([], make_context(), container)
        assert "Употреба" in result

    async def test_question_too_long_returns_error(self) -> None:
        container = Container()
        container.register("settings", SimpleNamespace(ai_max_prompt_length=10))
        result = await commands.cmd_consensus(["дълъг", "въпрос", "тук"], make_context(), container)
        assert "твърде дълга" in result

    async def test_missing_ai_router_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_consensus(["hi"], make_context(), container)
        assert "не е наличен" in result

    async def test_no_providers_registered_returns_friendly_message(self) -> None:
        container = Container()
        container.register("ai_router", make_router())
        result = await commands.cmd_consensus(["hi"], make_context(), container)
        assert "не е наличен" in result

    async def test_returns_single_provider_response_with_note(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="Тестов отговор."))
        container.register("ai_router", router)

        result = await commands.cmd_consensus(["Ще", "расте", "ли", "bitcoin?"], make_context(), container)

        assert "Тестов отговор." in result
        assert "mock" in result
        assert "само един AI provider" in result

    async def test_returns_multiple_provider_responses_without_note(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock1", MockAIProvider(response_content="Отговор 1"))
        router.register_provider("mock2", MockAIProvider(response_content="Отговор 2"))
        container.register("ai_router", router)

        result = await commands.cmd_consensus(["hi"], make_context(), container)

        assert "Отговор 1" in result
        assert "Отговор 2" in result
        assert "само един AI provider" not in result

    async def test_all_providers_fail_returns_friendly_message(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(should_fail=RuntimeError("boom")))
        container.register("ai_router", router)

        result = await commands.cmd_consensus(["hi"], make_context(), container)

        assert "Нито един AI provider" in result


class TestCmdConsensusAIGuard:
    """Task 030: /consensus must be protected by the same AI Guard used
    by /ask, /explain, and /research — guard_request() must run before
    ConsensusEngine.get_consensus() is ever called, so a rejected
    request never reaches any provider."""

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

    async def test_guard_request_is_called_before_consensus_engine(self) -> None:
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

        import phoenix_core.ai.consensus as consensus_module
        original_get_consensus = consensus_module.ConsensusEngine.get_consensus

        async def recording_get_consensus(self, messages):
            calls.append("get_consensus")
            return await original_get_consensus(self, messages)

        consensus_module.ConsensusEngine.get_consensus = recording_get_consensus
        try:
            await commands.cmd_consensus(["hi"], make_context(), container)
        finally:
            consensus_module.ConsensusEngine.get_consensus = original_get_consensus

        assert calls == ["guard_request", "get_consensus"]

    async def test_rejected_guard_prevents_consensus_engine_call(self) -> None:
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

        import phoenix_core.ai.consensus as consensus_module
        original_get_consensus = consensus_module.ConsensusEngine.get_consensus
        fake_get_consensus = _make_asserting_get_consensus()
        consensus_module.ConsensusEngine.get_consensus = fake_get_consensus

        try:
            result = await commands.cmd_consensus(["hi"], make_context(), container)
        finally:
            consensus_module.ConsensusEngine.get_consensus = original_get_consensus

        assert result  # a friendly rejection message was returned, not an empty/raised result
        assert fake_get_consensus.called is False

    async def test_authorized_request_reaches_consensus_engine(self) -> None:
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="Тестов отговор."))
        container.register("ai_router", router)

        guard = self._make_guard()
        container.register("ai_guard", guard)

        result = await commands.cmd_consensus(["hi"], make_context(), container)

        assert "Тестов отговор." in result

    async def test_existing_error_handling_intact_without_guard(self) -> None:
        """No ai_guard registered at all — /consensus must still work
        exactly as before Task 030 (ai_guard is optional, same as every
        other AI command)."""
        container = Container()
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="ok"))
        container.register("ai_router", router)

        result = await commands.cmd_consensus(["hi"], make_context(), container)

        assert "ok" in result


class _AlwaysAllowRateLimiter:
    def check(self, user_id):
        pass


class _AlwaysAllowCostGuard:
    def check_prompt(self, prompt):
        pass

    def check_context(self, messages):
        pass


def _make_asserting_get_consensus():
    async def fake_get_consensus(self, messages):
        fake_get_consensus.called = True
        raise AssertionError("ConsensusEngine.get_consensus must not be called for a rejected guard")
    fake_get_consensus.called = False
    return fake_get_consensus
