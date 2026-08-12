"""Unit tests for phoenix_core.services.research.research_capability.
Tests the capability directly — no Telegram objects, no real network
calls, no real API keys."""
from types import SimpleNamespace

import pytest

from phoenix_core.core.container import Container
from phoenix_core.services.research.research_capability import (
    ResearchAIError,
    ResearchNoDataError,
    ResearchResult,
    ResearchUnavailableError,
    run_research,
)
from phoenix_core.utils.exceptions import (
    AIProviderTimeoutError,
    ConfigurationError,
)


def _snapshot(symbol="BTC", price=100.0, empty=False):
    if empty:
        return SimpleNamespace(symbol=symbol, market=None, fear_greed=None, top_news=None, fees=None, is_empty=True)
    return SimpleNamespace(
        symbol=symbol,
        market=SimpleNamespace(price_usd=price, change_24h_pct=1.0),
        fear_greed=SimpleNamespace(value=50, classification="Neutral"),
        top_news=SimpleNamespace(title="Some headline", source="Test"),
        fees=None,
        is_empty=False,
    )


class FakeAggregator:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    async def get_snapshot(self, symbol):
        return self._snapshot


class FakeAIResponse:
    def __init__(self, content="AI narrative text", provider="fake-provider"):
        self.content = content
        self.provider = provider


class FakeAIRouter:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def chat(self, messages):
        if self._error is not None:
            raise self._error
        return self._response


def _dummy_build_prompt(snapshot, signals, evidence):
    return f"prompt for {snapshot.symbol}"


class TestSuccessfulResearchFlow:
    @pytest.mark.asyncio
    async def test_returns_research_result_with_expected_fields(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        result = await run_research("btc", container, _dummy_build_prompt, user_id=1)

        assert isinstance(result, ResearchResult)
        assert result.snapshot.symbol == "BTC"
        assert result.ai_text == "AI narrative text"
        assert result.provider == "fake-provider"
        assert result.evidence is not None
        assert isinstance(result.signals, dict)


class TestEmptySnapshot:
    @pytest.mark.asyncio
    async def test_empty_snapshot_raises_no_data_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot(empty=True)))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        with pytest.raises(ResearchNoDataError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)


class TestMissingServices:
    @pytest.mark.asyncio
    async def test_missing_aggregator_raises_unavailable_error(self) -> None:
        container = Container()
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        with pytest.raises(ResearchUnavailableError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)

    @pytest.mark.asyncio
    async def test_missing_ai_router_raises_unavailable_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))

        with pytest.raises(ResearchUnavailableError):
            await run_research("btc", container, _dummy_build_prompt, user_id=1)


class TestStrategyAndEvidenceIntegration:
    @pytest.mark.asyncio
    async def test_signals_and_evidence_are_derived_from_snapshot(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(response=FakeAIResponse()))

        result = await run_research("btc", container, _dummy_build_prompt, user_id=1)

        assert result.evidence.confidence in {"LOW", "MEDIUM", "HIGH"}
        assert "market" in result.evidence.available_sources


class TestAIFailureHandling:
    @pytest.mark.asyncio
    async def test_ai_timeout_raises_research_ai_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(error=AIProviderTimeoutError("timeout")))

        with pytest.raises(ResearchAIError) as exc_info:
            await run_research("btc", container, _dummy_build_prompt, user_id=1)
        assert exc_info.value.reason == "timeout"

    @pytest.mark.asyncio
    async def test_ai_not_configured_raises_research_ai_error(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(_snapshot()))
        container.register("ai_router", FakeAIRouter(error=ConfigurationError("no key")))

        with pytest.raises(ResearchAIError) as exc_info:
            await run_research("btc", container, _dummy_build_prompt, user_id=1)
        assert exc_info.value.reason == "not_configured"


class TestNoTelegramDependency:
    def test_module_has_no_telegram_import_statements(self) -> None:
        import phoenix_core.services.research.research_capability as module
        source = module.__file__
        with open(source, "r", encoding="utf-8") as f:
            lines = f.readlines()
        import_lines = [
            line for line in lines
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        telegram_imports = [line for line in import_lines if "telegram" in line.lower()]
        assert telegram_imports == [], f"Found Telegram import(s): {telegram_imports}"
