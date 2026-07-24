"""Unit tests for cmd_crypto, cmd_brief, and natural-language crypto routing in cmd_ask."""
from typing import List, Optional
import pytest
from phoenix_core.ai.base import AIResponse
from phoenix_core.core.container import Container
from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import CryptoError, CryptoNotFoundError, CryptoRateLimitError

pytestmark = pytest.mark.asyncio


class FakeCryptoProvider(CryptoProvider):
    def __init__(self, should_fail: Optional[Exception] = None) -> None:
        self._should_fail = should_fail
        self.calls: List[str] = []

    @property
    def name(self) -> str:
        return "fake"

    async def get_price(self, symbol: str) -> CryptoPrice:
        self.calls.append(f"get_price:{symbol}")
        if self._should_fail:
            raise self._should_fail
        return CryptoPrice(symbol=symbol.upper(), name=symbol, price_usd=100.0, change_24h_pct=1.0, last_updated="now")

    async def get_market(self, symbol: str) -> CryptoMarket:
        self.calls.append(f"get_market:{symbol}")
        if self._should_fail:
            raise self._should_fail
        if symbol == "unknown":
            raise CryptoNotFoundError("not found")
        return CryptoMarket(
            symbol=symbol.upper(), name="Bitcoin" if symbol == "btc" else symbol.capitalize(),
            price_usd=65000.0, change_24h_pct=2.31, market_cap_usd=1_200_000_000_000,
            volume_24h_usd=30_000_000_000, last_updated="2026-07-23 00:00:00 UTC",
        )

    async def get_top_coins(self, limit: int = 10) -> List[CryptoMarket]:
        self.calls.append(f"get_top_coins:{limit}")
        if self._should_fail:
            raise self._should_fail
        return [CryptoMarket(symbol="BTC", name="Bitcoin", price_usd=65000.0, change_24h_pct=1.0,
                              market_cap_usd=1_000_000_000_000, volume_24h_usd=10_000_000_000, last_updated="now")][:limit]

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


def make_context() -> CommandContext:
    return CommandContext(user_id=1, chat_id=1, command="crypto")


class TestCmdCryptoUsage:
    async def test_no_args_returns_usage_message(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeCryptoProvider())
        result = await commands.cmd_crypto([], make_context(), container)
        assert "Употреба" in result

    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_crypto(["btc"], make_context(), container)
        assert "не е конфигуриран" in result


class TestCmdCryptoSymbol:
    async def test_known_symbol_returns_formatted_market_data(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeCryptoProvider())
        result = await commands.cmd_crypto(["btc"], make_context(), container)
        assert "Bitcoin (BTC)" in result
        assert "Price:" in result
        assert "Market Cap:" in result
        assert "24h Volume:" in result
        assert "Last Updated:" in result

    async def test_unknown_symbol_returns_friendly_message(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeCryptoProvider())
        result = await commands.cmd_crypto(["unknown"], make_context(), container)
        assert "Непознат крипто символ" in result

    async def test_provider_error_returns_generic_message(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeCryptoProvider(should_fail=CryptoError("boom")))
        result = await commands.cmd_crypto(["btc"], make_context(), container)
        assert "грешка" in result.lower()


class TestCmdCryptoTop:
    async def test_top_returns_formatted_list(self) -> None:
        container = Container()
        provider = FakeCryptoProvider()
        container.register("crypto_provider", provider)
        result = await commands.cmd_crypto(["top"], make_context(), container)
        assert "Bitcoin (BTC)" in result
        assert "get_top_coins:10" in provider.calls

    async def test_top_with_custom_limit(self) -> None:
        container = Container()
        provider = FakeCryptoProvider()
        container.register("crypto_provider", provider)
        await commands.cmd_crypto(["top", "5"], make_context(), container)
        assert "get_top_coins:5" in provider.calls


class TestAskNaturalLanguageCryptoRouting:
    async def test_price_question_uses_crypto_provider_not_ai(self) -> None:
        container = Container()

        class FailingAIRouter:
            async def chat(self, **kwargs):
                raise AssertionError("AI provider should not be called for a crypto price question")

        container.register("ai_router", FailingAIRouter())
        container.register("crypto_provider", FakeCryptoProvider())
        result = await commands.cmd_ask(["Колко", "струва", "bitcoin?"], make_context(), container)
        assert "Bitcoin (BTC)" in result

    async def test_non_crypto_question_still_uses_ai(self) -> None:
        container = Container()

        class StubAIRouter:
            async def chat(self, **kwargs):
                return AIResponse(content="42", provider="stub", model="stub-model")

        container.register("ai_router", StubAIRouter())
        container.register("crypto_provider", FakeCryptoProvider())
        result = await commands.cmd_ask(["Какво", "е", "смисълът", "на", "живота?"], make_context(), container)
        assert "42" in result


class FakeBriefCryptoProvider(CryptoProvider):
    """Fake provider for /brief tests: distinct BTC/ETH prices, and a
    10-coin get_top_coins universe with a clear gainers/losers spread so
    the top-5/bottom-5 sort in cmd_brief is unambiguous to assert on."""

    def __init__(self, should_fail: Optional[Exception] = None) -> None:
        self._should_fail = should_fail
        self.calls: List[str] = []

    @property
    def name(self) -> str:
        return "fake-brief"

    async def get_price(self, symbol: str) -> CryptoPrice:
        raise NotImplementedError

    async def get_market(self, symbol: str) -> CryptoMarket:
        self.calls.append(f"get_market:{symbol}")
        if self._should_fail:
            raise self._should_fail
        prices = {"btc": 65241.0, "eth": 3412.0}
        changes = {"btc": 1.8, "eth": -0.6}
        return CryptoMarket(
            symbol=symbol.upper(), name=symbol.upper(), price_usd=prices.get(symbol, 100.0),
            change_24h_pct=changes.get(symbol, 0.0), market_cap_usd=1_000_000_000,
            volume_24h_usd=1_000_000, last_updated="now",
        )

    async def get_top_coins(self, limit: int = 10) -> List[CryptoMarket]:
        self.calls.append(f"get_top_coins:{limit}")
        if self._should_fail:
            raise self._should_fail
        coins = [
            ("AAA", 10.0, 25.0), ("BBB", 5.0, 18.0), ("CCC", 2.0, 12.0),
            ("DDD", 1.0, 9.0), ("EEE", 3.0, 5.0),
            ("FFF", 4.0, -3.0), ("GGG", 6.0, -8.0), ("HHH", 7.0, -14.0),
            ("III", 8.0, -20.0), ("JJJ", 9.0, -30.0),
        ]
        return [
            CryptoMarket(symbol=sym, name=sym, price_usd=price, change_24h_pct=change,
                         market_cap_usd=1_000_000, volume_24h_usd=1_000_000, last_updated="now")
            for sym, price, change in coins
        ][:limit]

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class TestCmdBrief:
    async def test_not_configured_returns_friendly_message(self) -> None:
        container = Container()
        result = await commands.cmd_brief([], make_context(), container)
        assert "не е конфигуриран" in result

    async def test_returns_btc_and_eth_prices(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeBriefCryptoProvider())
        result = await commands.cmd_brief([], make_context(), container)
        assert "BTC" in result
        assert "ETH" in result
        assert "Phoenix Morning Brief" in result

    async def test_returns_top_5_gainers_and_losers(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeBriefCryptoProvider())
        result = await commands.cmd_brief([], make_context(), container)
        assert "Top Gainers" in result
        assert "Top Losers" in result
        assert "AAA" in result
        assert "JJJ" in result

    async def test_provider_error_returns_generic_message(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeBriefCryptoProvider(should_fail=CryptoError("boom")))
        result = await commands.cmd_brief([], make_context(), container)
        assert "грешка" in result.lower()

    async def test_rate_limit_returns_friendly_message(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeBriefCryptoProvider(should_fail=CryptoRateLimitError("rate")))
        result = await commands.cmd_brief([], make_context(), container)
        assert "лимит" in result.lower()

    async def test_includes_last_updated_timestamp(self) -> None:
        container = Container()
        container.register("crypto_provider", FakeBriefCryptoProvider())
        result = await commands.cmd_brief([], make_context(), container)
        assert "Последна актуализация" in result
