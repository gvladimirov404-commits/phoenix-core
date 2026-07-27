"""FeesProvider — abstraction for Bitcoin network fee estimates, plus
MempoolSpaceFeesProvider, backed by the free, no-API-key mempool.space
endpoint (Task 020, /gas). CoinGecko's free tier has no Ethereum gas
endpoint, and Etherscan's gas oracle requires an API key — mempool.space's
Bitcoin fee estimates need neither, so /gas reports Bitcoin network fees.
Mirrors CoinGeckoProvider's shape (httpx client, retries, TTLCache) and
reuses the existing Crypto* exception hierarchy.
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

DEFAULT_BASE_URL = "https://mempool.space/api"
DEFAULT_CACHE_TTL_SECONDS = 60.0
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


@dataclass
class FeeEstimate:
    fastest_sat_vb: float
    half_hour_sat_vb: float
    hour_sat_vb: float
    economy_sat_vb: float


class FeesProvider(ABC):
    """Abstract base class for network fee providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_recommended_fees(self) -> FeeEstimate: ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]: ...


class MempoolSpaceFeesProvider(FeesProvider):
    """mempool.space-backed FeesProvider. Free, no API key required."""

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
        return "mempool.space"

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

    async def get_recommended_fees(self) -> FeeEstimate:
        cache_key = "fees:recommended"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        data = await self._get_with_retries("/v1/fees/recommended", {})
        try:
            estimate = FeeEstimate(
                fastest_sat_vb=float(data["fastestFee"]), half_hour_sat_vb=float(data["halfHourFee"]),
                hour_sat_vb=float(data["hourFee"]), economy_sat_vb=float(data["economyFee"]),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise CryptoInvalidResponseError(f"mempool.space response missing expected fields: {e}") from e

        self._cache.set(cache_key, estimate)
        return estimate

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
                last_error = CryptoTimeoutError(f"mempool.space request timed out: {e}")
            except httpx.TransportError as e:
                last_error = CryptoConnectionError(f"mempool.space connection failed: {e}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise CryptoInvalidResponseError(f"mempool.space returned non-JSON response: {e}") from e
                if response.status_code == 429:
                    last_error = CryptoRateLimitError("mempool.space rate limit exceeded")
                elif response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = CryptoError(f"mempool.space server error (HTTP {response.status_code})")
                else:
                    raise CryptoError(f"mempool.space request failed (HTTP {response.status_code}): {response.text}")
            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug("mempool.space request failed, retrying", attempt=attempt, max_retries=self.max_retries, backoff_seconds=backoff)
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error

    async def __aenter__(self) -> "MempoolSpaceFeesProvider":
        return self

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        await self.close()
