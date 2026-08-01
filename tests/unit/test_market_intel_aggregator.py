"""Unit tests for MarketIntelligenceAggregator (Roadmap item 2 / TASK-021 Part 9)."""
from typing import List, Optional

import pytest

from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.services.intel.aggregator import MarketIntelligenceAggregator
from phoenix_core.services.intel.feargreed_provider import FearGreedProvider, FearGreedReading
from phoenix_core.services.intel.fees_provider import FeeEstimate, FeesProvider
from phoenix_core.services.intel.news_provider import NewsItem, NewsProvider
from phoenix_core.utils.exceptions import CryptoError

pytestmark = pytest.mark.asyncio


class FakeCryptoProvider(CryptoProvider):
    def __init__(self, should_fail: Optional[Exception] = None) -> None:
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

    async def get_top_coins(self, limit: int = 10) -> List[CryptoMarket]:
        raise NotImplementedError

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class FakeFearGreedProvider(FearGreedProvider):
    def __init__(self, should_fail: Optional[Exception] = None) -> None:
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake-feargreed"

    async def get_current(self) -> FearGreedReading:
        if self._should_fail:
            raise self._should_fail
        return FearGreedReading(value=27, classification="Fear", timestamp="1721890000")

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


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


class FakeNewsProvider(NewsProvider):
    def __init__(self, should_fail: Optional[Exception] = None) -> None:
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake-news"

    async def get_news(self, symbol: str, limit: int = 5) -> List[NewsItem]:
        if self._should_fail:
            raise self._should_fail
        return [
            NewsItem(
                title="Bitcoin Falls",
                summary="...",
                url="https://example.com/1",
                published_at="2026-08-01",
                source="ExampleWire",
            )
        ]

    async def health_check(self):
        return {"status": "configured", "provider": self.name}


class TestGetSnapshot:
    async def test_all_sources_succeed_returns_full_snapshot(self) -> None:
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProvider(),
            feargreed_provider=FakeFearGreedProvider(),
            fees_provider=FakeFeesProvider(),
            news_provider=FakeNewsProvider(),
        )
        snapshot = await aggregator.get_snapshot("btc")
        assert snapshot.symbol == "BTC"
        assert snapshot.market is not None
        assert snapshot.fear_greed is not None
        assert snapshot.fees is not None
        assert snapshot.top_news is not None
        assert snapshot.is_empty is False

    async def test_single_source_failure_is_isolated(self) -> None:
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProvider(),
            feargreed_provider=FakeFearGreedProvider(),
            fees_provider=FakeFeesProvider(should_fail=CryptoError("mempool down")),
            news_provider=FakeNewsProvider(),
        )
        snapshot = await aggregator.get_snapshot("btc")
        assert snapshot.market is not None
        assert snapshot.fear_greed is not None
        assert snapshot.fees is None
        assert snapshot.top_news is not None
        assert snapshot.is_empty is False

    async def test_all_sources_fail_snapshot_is_empty(self) -> None:
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProvider(should_fail=CryptoError("down")),
            feargreed_provider=FakeFearGreedProvider(should_fail=CryptoError("down")),
            fees_provider=FakeFeesProvider(should_fail=CryptoError("down")),
            news_provider=FakeNewsProvider(should_fail=CryptoError("down")),
        )
        snapshot = await aggregator.get_snapshot("btc")
        assert snapshot.is_empty is True

    async def test_fees_only_fetched_for_btc(self) -> None:
        aggregator = MarketIntelligenceAggregator(
            crypto_provider=FakeCryptoProvider(),
            fees_provider=FakeFeesProvider(),
        )
        snapshot = await aggregator.get_snapshot("eth")
        assert snapshot.fees is None

    async def test_optional_providers_none_are_skipped_gracefully(self) -> None:
        aggregator = MarketIntelligenceAggregator(crypto_provider=FakeCryptoProvider())
        snapshot = await aggregator.get_snapshot("btc")
        assert snapshot.market is not None
        assert snapshot.fear_greed is None
        assert snapshot.fees is None
        assert snapshot.top_news is None
