"""
MarketIntelligenceAggregator — combines already-available crypto/intel
providers into a single "what's happening with this coin right now"
snapshot (TASK-021 Part 9 / Roadmap item 2).

Synthesizes CryptoProvider (price/market), FeesProvider (BTC network fees),
FearGreedProvider (overall market sentiment), and NewsProvider (latest
headline) - no new external data source, purely composition of what
Phoenix already fetches individually via /crypto, /gas, /fear, /news.

The four sub-sources are fetched concurrently (TASK-022 speed
optimization) rather than one after another — each is still wrapped in
_safe_call so one slow/failing provider never blocks or blanks out the
others, but the total wait time is now roughly the slowest single call
instead of the sum of all four.
"""
import asyncio
from dataclasses import dataclass
from typing import Optional, TypeVar

from phoenix_core.services.crypto.base import CryptoMarket, CryptoProvider
from phoenix_core.services.intel.feargreed_provider import FearGreedProvider, FearGreedReading
from phoenix_core.services.intel.fees_provider import FeeEstimate, FeesProvider
from phoenix_core.services.intel.news_provider import NewsItem, NewsProvider
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class MarketSnapshot:
    """Consolidated view of a single coin plus overall market context.

    Any field may be None - each sub-source is fetched independently, so a
    single unavailable provider never blanks out the whole snapshot.
    """

    symbol: str
    market: Optional[CryptoMarket]
    fear_greed: Optional[FearGreedReading]
    fees: Optional[FeeEstimate]
    top_news: Optional[NewsItem]

    @property
    def is_empty(self) -> bool:
        """True only if every single sub-source failed."""
        return self.market is None and self.fear_greed is None and self.fees is None and self.top_news is None


class MarketIntelligenceAggregator:
    """Gathers a consolidated market snapshot from already-available providers.

    Every sub-source is fetched concurrently and failures are isolated -
    one provider being slow or unavailable (e.g. mempool.space) must never
    prevent the others from returning their part of the snapshot, and must
    never make the whole snapshot wait longer than the slowest single call.
    Owns no HTTP client of its own; each provider it composes has its own
    lifecycle managed elsewhere.
    """

    def __init__(
        self,
        crypto_provider: CryptoProvider,
        feargreed_provider: Optional[FearGreedProvider] = None,
        fees_provider: Optional[FeesProvider] = None,
        news_provider: Optional[NewsProvider] = None,
    ) -> None:
        self._crypto_provider = crypto_provider
        self._feargreed_provider = feargreed_provider
        self._fees_provider = fees_provider
        self._news_provider = news_provider

    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Return a MarketSnapshot for `symbol`. Network fees are only
        included when `symbol` is BTC (FeesProvider is Bitcoin-specific).
        All configured sub-sources are fetched concurrently."""
        include_fees = self._fees_provider is not None and symbol.strip().lower() == "btc"

        market_task = self._safe_call(self._crypto_provider.get_market(symbol))
        fear_greed_task = (
            self._safe_call(self._feargreed_provider.get_current())
            if self._feargreed_provider is not None
            else self._none_result()
        )
        fees_task = (
            self._safe_call(self._fees_provider.get_recommended_fees())
            if include_fees
            else self._none_result()
        )
        news_task = (
            self._safe_call(self._news_provider.get_news(symbol, limit=1))
            if self._news_provider is not None
            else self._none_result()
        )

        market, fear_greed, fees, news_items = await asyncio.gather(
            market_task, fear_greed_task, fees_task, news_task
        )

        top_news = news_items[0] if news_items else None

        return MarketSnapshot(
            symbol=symbol.strip().upper(),
            market=market,
            fear_greed=fear_greed,
            fees=fees,
            top_news=top_news,
        )

    @staticmethod
    async def _safe_call(awaitable):
        try:
            return await awaitable
        except Exception as e:
            logger.warning(
                "Market intelligence sub-source failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    @staticmethod
    async def _none_result():
        return None
