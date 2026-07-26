"""FearGreedProvider — abstraction for the Crypto Fear & Greed Index, plus
AlternativeMeFearGreedProvider, backed by the free, no-API-key alternative.me
endpoint (Task 020, /fear). Mirrors CoinGeckoProvider's shape (httpx client,
retries, TTLCache) and reuses the existing Crypto* exception hierarchy.
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Dict, Optional, Type

import httpx

from phoenix_core.services.crypto.cache import TTLCache
from phoenix_core.utils.exceptions import (
    CryptoConnectionError,
    CryptoError,
    CryptoInvalidResponseError,
    CryptoRateLimitError,
    CryptoTimeoutError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.alternative.me"
DEFAULT_CACHE_TTL_SECONDS = 300.0  # the index only updates once a day; a longer TTL is appropriate
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

_CLASSIFICATION_EXPLANATIONS_BG = {
    "Extreme Fear": "Пазарът е в паника — исторически това често (но не гарантирано) е предшествало възстановяване.",
    "Fear": "Инвеститорите са предпазливи — повишена несигурност на пазара.",
    "Neutral": "Пазарът е балансиран — нито страх, нито алчност доминират.",
    "Greed": "Инвеститорите са уверени — расте апетитът за риск.",
    "Extreme Greed": "Пазарът е в еуфория — исторически това често (но не гарантирано) е предшествало корекция.",
}


@dataclass
class FearGreedReading:
    value: int
    classification: str
    timestamp: Optional[str]


class FearGreedProvider(ABC):
    """Abstract base class for Fear & Greed Index providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_current(self) -> FearGreedReading: ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]: ...


def explain_classification(classification: str) -> str:
    """Short Bulgarian explanation for a Fear & Greed classification label."""
    return _CLASSIFICATION_EXPLANATIONS_BG.get(classification, "")


class AlternativeMeFearGreedProvider(FearGreedProvider):
    """alternative.me-backed FearGreedProvider. Free, no API key required."""

    def __init__(
        self, base_url: Optional[str] = None, timeout: int = 15,
        max_retries: int = 2, cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    @property
    def name(self) -> str:
        return "alternative.me"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def stop(self) -> None:
        await self.close()

    async def get_current(self) -> FearGreedReading:
        cache_key = "fng:current"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self._get_with_retries("/fng/", {"limit": 1})
        results = data.get("data", [])
        if not results:
            raise CryptoInvalidResponseError("alternative.me returned no Fear & Greed data")

        item = results[0]
        try:
            reading = FearGreedReading(
                value=int(item["value"]), classification=item["value_classification"],
                timestamp=item.get("timestamp"),
            )
        except (KeyError, ValueError) as e:
            raise CryptoInvalidResponseError(f"alternative.me response missing expected fields: {e}") from e

        self._cache.set(cache_key, reading)
        return reading

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "configured", "provider": self.name, "base_url": self.base_url, "cache_entries": len(self._cache)}

    async def _get_with_retries(self, path: str, params: Dict[str, Any]) -> Any:
        client = self._get_client()
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= self.max_retries:
            try:
                response = await client.get(path, params=params)
            except httpx.TimeoutException as e:
                last_error = CryptoTimeoutError(f"alternative.me request timed out: {e}")
            except httpx.TransportError as e:
                last_error = CryptoConnectionError(f"alternative.me connection failed: {e}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise CryptoInvalidResponseError(f"alternative.me returned non-JSON response: {e}") from e
                if response.status_code == 429:
                    last_error = CryptoRateLimitError("alternative.me rate limit exceeded")
                elif response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = CryptoError(f"alternative.me server error (HTTP {response.status_code})")
                else:
                    raise CryptoError(f"alternative.me request failed (HTTP {response.status_code}): {response.text}")
            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug("alternative.me request failed, retrying", attempt=attempt, max_retries=self.max_retries, backoff_seconds=backoff)
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error

    async def __aenter__(self) -> "AlternativeMeFearGreedProvider":
        return self

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        await self.close()
