"""Unit tests for ConsensusEngine (Roadmap item 5 / TASK-021 Part 9)."""
import pytest

from phoenix_core.ai.consensus import ConsensusEngine
from phoenix_core.ai.router import AIRouter

from .conftest import MockAIProvider

pytestmark = pytest.mark.asyncio


def make_router() -> AIRouter:
    return AIRouter(providers=[], default_provider="mock")


class TestGetConsensus:
    async def test_single_provider_returns_one_response(self) -> None:
        router = make_router()
        router.register_provider("mock", MockAIProvider(response_content="Отговор 1"))
        engine = ConsensusEngine(router)

        result = await engine.get_consensus([{"role": "user", "content": "Ще расте ли bitcoin?"}])

        assert result.provider_count == 1
        assert "mock" in result.responses
        assert result.responses["mock"].content == "Отговор 1"
        assert not result.errors

    async def test_multiple_providers_returns_all_responses(self) -> None:
        router = make_router()
        router.register_provider("mock1", MockAIProvider(response_content="Отговор 1"))
        router.register_provider("mock2", MockAIProvider(response_content="Отговор 2"))
        engine = ConsensusEngine(router)

        result = await engine.get_consensus([{"role": "user", "content": "hi"}])

        assert result.provider_count == 2
        assert result.responses["mock1"].content == "Отговор 1"
        assert result.responses["mock2"].content == "Отговор 2"
        assert not result.errors

    async def test_provider_failure_is_isolated(self) -> None:
        router = make_router()
        router.register_provider("mock1", MockAIProvider(response_content="Отговор 1"))
        router.register_provider("mock2", MockAIProvider(should_fail=RuntimeError("boom")))
        engine = ConsensusEngine(router)

        result = await engine.get_consensus([{"role": "user", "content": "hi"}])

        assert result.responses["mock1"].content == "Отговор 1"
        assert "mock2" in result.errors
        assert "mock2" not in result.responses

    async def test_no_providers_returns_empty_result(self) -> None:
        router = make_router()
        engine = ConsensusEngine(router)

        result = await engine.get_consensus([{"role": "user", "content": "hi"}])

        assert result.provider_count == 0
        assert not result.responses
        assert not result.errors
