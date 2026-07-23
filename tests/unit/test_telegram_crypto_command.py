"""Unit tests for cmd_crypto and natural-language crypto routing in cmd_ask."""
from typing import List, Optional
import pytest
from phoenix_core.ai.base import AIResponse
from phoenix_core.core.container import Container
from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.telegram import commands
from phoenix_core.telegram.context import CommandContext
from phoenix_core.utils.exceptions import CryptoError, CryptoNotFoundError

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
