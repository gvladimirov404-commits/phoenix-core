"""Unit tests for _build_copilot_prompt and cmd_copilot (Trading Copilot roadmap item, final TASK-021 item)."""
import pytest

from phoenix_core.ai.router import AIRouter
from phoenix_core.core.container import Container
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.intel.aggregator import MarketSnapshot
from phoenix_core.services.intel.feargreed_provider import FearGreedReading
from phoenix_core.services.intel.news_provider import NewsItem
from phoenix_core.services.strategy.registry import StrategyRegistry
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import AIProviderTimeoutError, ConfigurationError

from .conftest import MockAIProvider

pytestmark = pytest.mark.asyncio


def make_context(user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=user_id, command="test")


def make_router(response_content: str = "Тестов брифинг.", should_fail=None) -> AIRouter:
    router = AIRouter(providers=[], default_provider="mock")
    router.register_provider("mock", MockAIProvider(response_content=response_content, should_fail=should_fail))
    return router


class FakeAggregator:
    def __init__(self, snapshot=None, should_fail=None):
        self._snapshot = snapshot
        self._should_fail = should_fail

    async def get_snapshot(self, symbol):
        if self._should_fail:
            raise self._should_fail
        return self._snapshot


def full_snapshot(symbol: str = "BTC") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        market=CryptoMarket(
            symbol=symbol, name=symbol, price_usd=62948.0, change_24h_pct=-1.2,
            market_cap_usd=1.0, volume_24h_usd=1.0, last_updated="2026-08-02",
        ),
        fear_greed=FearGreedReading(value=27, classification="Fear", timestamp="0"),
        fees=None,
        top_news=NewsItem(
            title="Bitcoin Falls", summary="...", url="https://x.com/1",
            published_at="2026-08-02", source="ExampleWire",
        ),
    )


def empty_snapshot(symbol: str = "BTC") -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, market=None, fear_greed=None, fees=None, top_news=None)


class TestBuildCopilotPrompt:
    def test_includes_price_sentiment_news_and_strategy_signals(self) -> None:
        snapshot = full_snapshot()
        signals = StrategyRegistry().evaluate_all(snapshot)
        prompt = commands._build_copilot_prompt(snapshot, signals)
        assert "BTC" in prompt
        assert "62948.0" in prompt
        assert "-1.20%" in prompt
        assert "27/100" in prompt
        assert "Fear" in prompt
        assert "Bitcoin Falls" in prompt
        assert "ExampleWire" in prompt
        assert "Strategy Lab" in prompt
        assert "momentum" in prompt
        assert "не давай пряка препоръка" in prompt

    def test_handles_missing_market_data_gracefully(self) -> None:
        prompt = commands._build_copilot_prompt(empty_snapshot(), {})
        assert "Няма налична информация за цената" in prompt


class TestCmdCopilot:
    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        result = await commands.cmd_copilot([], make_context(), container)
        assert "Употреба" in result

    async def test_missing_aggregator_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_empty_snapshot_returns_no_data_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=empty_snapshot()))
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "Не успях" in result

    async def test_missing_ai_router_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_returns_ai_briefing_with_disclaimer(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(response_content="Разбираем брифинг за BTC."))
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "Разбираем брифинг за BTC." in result
        assert "✈️ Trading Copilot — BTC" in result
        assert "не е финансов съвет" in result
        assert "Provider: mock" in result

    async def test_ai_provider_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(should_fail=ConfigurationError("no key")))
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_ai_timeout_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        container.register("ai_router", make_router(should_fail=AIProviderTimeoutError("timeout")))
        result = await commands.cmd_copilot(["btc"], make_context(), container)
        assert "отне" in result.lower()
