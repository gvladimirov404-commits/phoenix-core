"""Market intelligence providers (Task 020): crypto news, Fear & Greed Index,
and Bitcoin network fees. Sibling package to services/crypto — reuses the
same TTLCache implementation and the existing Crypto* exception hierarchy
(these are conceptually still "crypto data provider" failures), rather than
introducing a parallel set of types."""
from phoenix_core.services.intel.feargreed_provider import (
    AlternativeMeFearGreedProvider,
    FearGreedProvider,
    FearGreedReading,
)
from phoenix_core.services.intel.fees_provider import (
    FeeEstimate,
    FeesProvider,
    MempoolSpaceFeesProvider,
)
from phoenix_core.services.intel.news_provider import (
    CryptoPanicNewsProvider,
    NewsItem,
    NewsProvider,
)

__all__ = [
    "NewsItem", "NewsProvider", "CryptoPanicNewsProvider",
    "FearGreedReading", "FearGreedProvider", "AlternativeMeFearGreedProvider",
    "FeeEstimate", "FeesProvider", "MempoolSpaceFeesProvider",
]
