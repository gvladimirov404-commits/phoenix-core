"""Unit tests for cmd_explain and _build_explain_prompt (Roadmap item 1 / TASK-021 Part 9)."""
from typing import List, Optional

import pytest

from phoenix_core.ai.router import AIRouter
from phoenix_core.core.container import Container
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.intel.aggregator import MarketSnapshot
from phoenix_core.services.intel.feargreed_provider import FearGreedReading
from phoenix_core.services.intel.fees_provider import FeeEstimate
from phoenix_core.services.intel.news_provider import NewsItem
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import AIProviderTimeoutError, ConfigurationError

from .conftest import MockAIProvider

pytestmark = pytest.mark.asyncio


def make_context(user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=user_id, command="test")


class FakeAggregator:
    def __init__(self, snapshot: Optional[MarketSnapshot] = None, should_fail: Optional[Exception] = None) -> None:
        self._snapshot = snapshot
        self._should_fail = should_fail
        self.calls: List[str] = []

    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        self.calls.append(symbol)
        if self._should_fail:
            raise self._should_fail
        return self._snapshot


def full_snapshot(symbol: str = "BTC") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        market=CryptoMarket(
            symbol=symbol,
            name=symbol,
            price_usd=62948.0,
            change_24h_pct=-1.2,
            market_cap_usd=1_000_000.0,
            volume_24h_usd=500_000.0,
            last_updated="2026-08-01",
        ),
        fear_greed=FearGreedReading(value=27, classification="Fear", timestamp="1721890000"),
        fees=FeeEstimate(fastest_sat_vb=45.0, half_hour_sat_vb=30.0, hour_sat_vb=20.0, economy_sat_vb=5.0),
        top_news=NewsItem(
            title="Bitcoin Falls",
            summary="...",
            url="https://example.com/1",
            published_at="2026-08-01",
            source="ExampleWire",
        ),
    )


def empty_snapshot(symbol: str = "BTC") -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, market=None, fear_greed=None, fees=None, top_news=None)


def make_router(response_content: str = "Обяснение тест.", should_fail: Optional[Exception] = None) -> AIRouter:
    router = AIRouter(providers=[], default_provider="mock")
    router.register_provider("mock", MockAIProvider(response_content=response_content, should_fail=should_fail))
    return router


class TestBuildExplainPrompt:
    def test_includes_price_change_sentiment_fees_and_news(self) -> None:
        prompt = commands._build_explain_prompt(full_snapshot())
        assert "BTC" in prompt
        assert "62948.0" in prompt
        assert "-1.20%" in prompt
        assert "27/100" in prompt
        assert "Fear" in prompt
        assert "45" in prompt
        assert "Bitcoin Falls" in prompt
        assert "ExampleWire" in prompt

    def test_handles_missing_market_data_gracefully(self) -> None:
        snapshot = MarketSnapshot(symbol="ETH", market=None, fear_greed=None, fees=None, top_news=None)
        prompt = commands._build_explain_prompt(snapshot)
        assert "ETH" in prompt
        assert "Няма налична информация за цената" in prompt


class TestCmdExplain:
    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        result = await commands.cmd_explain([], make_context(), container)
        assert "Употреба" in result

    async def test_missing_aggregator_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_empty_snapshot_returns_no_data_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=empty_snapshot()))
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "Не успях" in result

    async def test_missing_ai_router_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_returns_ai_generated_explanation(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(response_content="Тестово обяснение за BTC."))
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "Тестово обяснение за BTC." in result
        assert "🧠 Обяснение за BTC" in result
        assert "Provider: mock" in result

    async def test_ai_provider_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(should_fail=ConfigurationError("no key")))
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_ai_timeout_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(should_fail=AIProviderTimeoutError("timeout")))
        result = await commands.cmd_explain(["btc"], make_context(), container)
        assert "отне" in result.lower()
