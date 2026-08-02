"""Unit tests for cmd_strategy (Strategy Lab roadmap item)."""
import pytest

from phoenix_core.core.container import Container
from phoenix_core.services.crypto.base import CryptoMarket
from phoenix_core.services.intel.aggregator import MarketSnapshot
from phoenix_core.services.intel.feargreed_provider import FearGreedReading
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext

pytestmark = pytest.mark.asyncio


def make_context(user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=user_id, command="test")


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
            symbol=symbol, name=symbol, price_usd=50000.0, change_24h_pct=1.0,
            market_cap_usd=1.0, volume_24h_usd=1.0, last_updated="2026-08-02",
        ),
        fear_greed=FearGreedReading(value=50, classification="Neutral", timestamp="0"),
        fees=None,
        top_news=None,
    )


def empty_snapshot(symbol: str = "BTC") -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, market=None, fear_greed=None, fees=None, top_news=None)


class TestCmdStrategy:
    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        result = await commands.cmd_strategy([], make_context(), container)
        assert "Употреба" in result

    async def test_missing_aggregator_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_strategy(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_empty_snapshot_returns_no_data_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=empty_snapshot()))
        result = await commands.cmd_strategy(["btc"], make_context(), container)
        assert "Не успях" in result

    async def test_unknown_strategy_name_returns_friendly_message(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_strategy(["btc", "does_not_exist"], make_context(), container)
        assert "Няма стратегия" in result

    async def test_single_named_strategy_returns_only_that_signal(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_strategy(["btc", "momentum"], make_context(), container)
        assert "momentum" in result
        assert "fear_greed_contrarian" not in result

    async def test_no_strategy_name_returns_all_signals(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_strategy(["btc"], make_context(), container)
        assert "momentum" in result
        assert "fear_greed_contrarian" in result

    async def test_result_includes_disclaimer(self) -> None:
        container = Container()
        container.register("market_intel_aggregator", FakeAggregator(snapshot=full_snapshot()))
        result = await commands.cmd_strategy(["btc"], make_context(), container)
        assert "не е финансов съвет" in result
