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
