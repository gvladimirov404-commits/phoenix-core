"""Unit tests for cmd_news, cmd_fear, cmd_gas, cmd_watch, and cmd_help (Task 020)."""
from typing import List, Optional

import pytest

from phoenix_core.core.container import Container
from phoenix_core.services.intel.feargreed_provider import FearGreedProvider, FearGreedReading
from phoenix_core.services.intel.fees_provider import FeeEstimate, FeesProvider
from phoenix_core.services.intel.news_provider import NewsItem, NewsProvider
from phoenix_core.services.watchlist.manager import WatchlistManager
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.telegram.dispatcher import CommandDispatcher
from phoenix_core.utils.exceptions import CryptoError, CryptoRateLimitError

pytestmark = pytest.mark.asyncio


def make_context(user_id: int = 1) -> CommandContext:
    return CommandContext(user_id=user_id, chat_id=user_id, command="test")


# ----------------------------------------------------------------------
# /news
# ----------------------------------------------------------------------

class FakeNewsProvider(NewsProvider):
    def __init__(self, should_fail: Optional[Exception] = None, empty: bool = False) -> None:
        self._should_fail = should_fail
        self._empty = empty
        self.calls: List[str] = []

    @property
    def name(self) -> str:
        return "fake-news"

    async def get_news(self, symbol: str, limit: int = 5) -> List[NewsItem]:
        self.calls.append(f"get_news:{symbol}:{limit}")
        if self._should_fail:
            raise self._should_fail
        if self._empty:
            return []
        return [
            NewsItem(title=f"Headline {i}", summary=f"Headline {i}", url=f"https://example.com/{i}", published_at="2026-07-25", source="ExampleWire")
            for i in range(1, limit + 1)
        ]

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class TestCmdNews:
    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_news(["btc"], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        container.register("news_provider", FakeNewsProvider())
        result = await commands.cmd_news([], make_context(), container)
        assert "Употреба" in result

    async def test_returns_five_news_items_with_links(self) -> None:
        container = Container()
        container.register("news_provider", FakeNewsProvider())
        result = await commands.cmd_news(["btc"], make_context(), container)
        assert "BTC" in result
        assert "https://example.com/1" in result
        assert "https://example.com/5" in result
        assert "ExampleWire" in result

    async def test_empty_results_returns_friendly_message(self) -> None:
        container = Container()
        container.register("news_provider", FakeNewsProvider(empty=True))
        result = await commands.cmd_news(["btc"], make_context(), container)
        assert "Няма намерени новини" in result

    async def test_provider_error_returns_generic_message(self) -> None:
        container = Container()
        container.register("news_provider", FakeNewsProvider(should_fail=CryptoError("boom")))
        result = await commands.cmd_news(["btc"], make_context(), container)
        assert "грешка" in result.lower()

    async def test_rate_limit_returns_friendly_message(self) -> None:
        container = Container()
        container.register("news_provider", FakeNewsProvider(should_fail=CryptoRateLimitError("rate")))
        result = await commands.cmd_news(["btc"], make_context(), container)
        assert "лимит" in result.lower()


# ----------------------------------------------------------------------
# /fear
# ----------------------------------------------------------------------

class FakeFearGreedProvider(FearGreedProvider):
    def __init__(self, reading: Optional[FearGreedReading] = None, should_fail: Optional[Exception] = None) -> None:
        self._reading = reading or FearGreedReading(value=72, classification="Greed", timestamp="1721890000")
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake-feargreed"

    async def get_current(self) -> FearGreedReading:
        if self._should_fail:
            raise self._should_fail
        return self._reading

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class TestCmdFear:
    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_fear([], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_returns_value_and_classification(self) -> None:
        container = Container()
        container.register("feargreed_provider", FakeFearGreedProvider())
        result = await commands.cmd_fear([], make_context(), container)
        assert "72" in result
        assert "Greed" in result

    async def test_includes_explanation_text(self) -> None:
        container = Container()
        container.register("feargreed_provider", FakeFearGreedProvider(
            FearGreedReading(value=10, classification="Extreme Fear", timestamp="1721890000")))
        result = await commands.cmd_fear([], make_context(), container)
        assert "паника" in result.lower()

    async def test_provider_error_returns_generic_message(self) -> None:
        container = Container()
        container.register("feargreed_provider", FakeFearGreedProvider(should_fail=CryptoError("boom")))
        result = await commands.cmd_fear([], make_context(), container)
        assert "грешка" in result.lower()


# ----------------------------------------------------------------------
# /gas
# ----------------------------------------------------------------------

class FakeFeesProvider(FeesProvider):
    def __init__(self, should_fail: Optional[Exception] = None) -> None:
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake-fees"

    async def get_recommended_fees(self) -> FeeEstimate:
        if self._should_fail:
            raise self._should_fail
        return FeeEstimate(fastest_sat_vb=45.0, half_hour_sat_vb=30.0, hour_sat_vb=20.0, economy_sat_vb=5.0)

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class TestCmdGas:
    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_gas([], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_returns_all_fee_tiers(self) -> None:
        container = Container()
        container.register("fees_provider", FakeFeesProvider())
        result = await commands.cmd_gas([], make_context(), container)
        assert "45" in result
        assert "30" in result
        assert "20" in result
        assert "5" in result
        assert "sat/vB" in result

    async def test_provider_error_returns_generic_message(self) -> None:
        container = Container()
        container.register("fees_provider", FakeFeesProvider(should_fail=CryptoError("boom")))
        result = await commands.cmd_gas([], make_context(), container)
        assert "грешка" in result.lower()


# ----------------------------------------------------------------------
# /watch
# ----------------------------------------------------------------------

class TestCmdWatch:
    async def test_unavailable_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_watch(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_no_args_on_empty_watchlist_returns_friendly_message(self) -> None:
        container = Container()
        container.register("watchlist_manager", WatchlistManager())
        result = await commands.cmd_watch([], make_context(user_id=1), container)
        assert "празен" in result

    async def test_adding_symbols_returns_full_watchlist(self) -> None:
        container = Container()
        container.register("watchlist_manager", WatchlistManager())
        result = await commands.cmd_watch(["btc", "eth", "sol"], make_context(user_id=1), container)
        assert "BTC" in result
        assert "ETH" in result
        assert "SOL" in result

    async def test_no_args_returns_previously_saved_watchlist(self) -> None:
        container = Container()
        manager = WatchlistManager()
        container.register("watchlist_manager", manager)
        await commands.cmd_watch(["btc"], make_context(user_id=42), container)
        result = await commands.cmd_watch([], make_context(user_id=42), container)
        assert "BTC" in result

    async def test_watchlists_are_isolated_per_user(self) -> None:
        container = Container()
        manager = WatchlistManager()
        container.register("watchlist_manager", manager)
        await commands.cmd_watch(["btc"], make_context(user_id=1), container)
        result = await commands.cmd_watch([], make_context(user_id=2), container)
        assert "празен" in result

    async def test_duplicate_symbols_are_not_repeated(self) -> None:
        container = Container()
        manager = WatchlistManager()
        container.register("watchlist_manager", manager)
        await commands.cmd_watch(["btc"], make_context(user_id=1), container)
        result = await commands.cmd_watch(["btc"], make_context(user_id=1), container)
        assert result.count("BTC") == 1


# ----------------------------------------------------------------------
# /help onboarding
# ----------------------------------------------------------------------

class TestCmdHelpOnboarding:
    async def test_includes_greeting_and_examples(self) -> None:
        container = Container()
        dispatcher = CommandDispatcher()
        dispatcher.register("watch", commands.cmd_watch, "Watchlist")
        container.register("command_dispatcher", dispatcher)
        result = await commands.cmd_help([], make_context(), container)
        assert "Добре дошъл" in result
        assert "/watch — Watchlist" in result
        assert "Колко струва bitcoin?" in result
        assert "/watch" in result
        assert "/research" in result
        assert "/copilot" in result
        assert "Предстои" not in result

from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.services.intel.aggregator import MarketIntelligenceAggregator


class FakeCryptoProviderForIntel(CryptoProvider):
    def __init__(self, should_fail=None) -> None:
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake-crypto"

    async def get_price(self, symbol: str) -> CryptoPrice:
        raise NotImplementedError

    async def get_market(self, symbol: str) -> CryptoMarket:
        if self._should_fail:
            raise self._should_fail
        return CryptoMarket(
            symbol=symbol.upper(),
            name=symbol.upper(),
            price_usd=62948.0,
            change_24h_pct=-1.2,
            market_cap_usd=1_000_000.0,
            volume_24h_usd=500_000.0,
            last_updated="2026-08-01",
        )

    async def get_top_coins(self, limit: int = 10):
        raise NotImplementedError

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


# ----------------------------------------------------------------------
# /intel
# ----------------------------------------------------------------------

class TestCmdIntel:
    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_intel(["btc"], make_context(), container)
        assert "не е наличен" in result

    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        aggregator = MarketIntelligenceAggregator(crypto_provider=FakeCryptoProviderForIntel())
        container.register("market_intel_aggregator", aggregator)
        result = await commands.cmd_intel([], make_context(), container)
        assert "Употреба" in result

    async def test_returns_price_sentiment_fees_and_news(self) -> None:
        container = Container()
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProviderForIntel(),
            feargreed_provider=FakeFearGreedProvider(),
            fees_provider=FakeFeesProvider(),
            news_provider=FakeNewsProvider(),
        )
        container.register("market_intel_aggregator", aggregator)
        result = await commands.cmd_intel(["btc"], make_context(), container)
        assert "BTC" in result
        assert "62,948.00" in result
        assert "72/100" in result
        assert "Greed" in result
        assert "45" in result
        assert "Headline 1" in result

    async def test_all_sub_sources_failing_returns_warning(self) -> None:
        container = Container()
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProviderForIntel(should_fail=CryptoError("down")),
        )
        container.register("market_intel_aggregator", aggregator)
        result = await commands.cmd_intel(["btc"], make_context(), container)
        assert "Не успях" in result
