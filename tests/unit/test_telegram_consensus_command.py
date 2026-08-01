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
