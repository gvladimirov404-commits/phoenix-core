"""CoinGeckoProvider — CryptoProvider implementation backed by the free CoinGecko public API (Task CRYPTO-001)."""
import asyncio
from datetime import datetime, timezone
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

import httpx

from phoenix_core.services.crypto.base import CryptoMarket, CryptoPrice, CryptoProvider
from phoenix_core.services.crypto.cache import TTLCache
from phoenix_core.utils.exceptions import (
    CryptoConnectionError,
    CryptoError,
    CryptoInvalidResponseError,
    CryptoNotFoundError,
    CryptoRateLimitError,
    CryptoTimeoutError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.coingecko.com/api/v3"
DEFAULT_CACHE_TTL_SECONDS = 60.0

_SYMBOL_TO_ID = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "bnb": "binancecoin",
    "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "ton": "the-open-network",
    "trx": "tron", "matic": "matic-network", "dot": "polkadot", "avax": "avalanche-2",
    "link": "chainlink", "ltc": "litecoin", "usdt": "tether", "usdc": "usd-coin",
}
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


def _resolve_id(symbol: str) -> str:
    key = symbol.strip().lower()
    return _SYMBOL_TO_ID.get(key, key)


def _format_timestamp(unix_ts: Optional[int]) -> Optional[str]:
    if unix_ts is None:
        return None
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _market_from_payload(item: Dict[str, Any]) -> CryptoMarket:
    try:
        return CryptoMarket(
            symbol=(item.get("symbol") or "").upper(),
            name=item.get("name", "—"),
            price_usd=item["current_price"],
            change_24h_pct=item.get("price_change_percentage_24h"),
            market_cap_usd=item.get("market_cap"),
            volume_24h_usd=item.get("total_volume"),
            last_updated=item.get("last_updated"),
            market_cap_rank=item.get("market_cap_rank"),
        )
    except KeyError as e:
        raise CryptoInvalidResponseError(f"CoinGecko response missing expected fields: {e}") from e


class CoinGeckoProvider(CryptoProvider):
    def __init__(self, base_url: Optional[str] = None, timeout: int = 15, max_retries: int = 2,
                 cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    @property
    def name(self) -> str:
        return "coingecko"

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

    async def get_price(self, symbol: str) -> CryptoPrice:
        coin_id = _resolve_id(symbol)
        cache_key = f"price:{coin_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true", "include_last_updated_at": "true"}
        data = await self._get_with_retries("/simple/price", params)
        if coin_id not in data:
            raise CryptoNotFoundError(f"Непознат крипто символ: {symbol}")
        coin_data = data[coin_id]
        try:
            price = CryptoPrice(
                symbol=symbol.upper(), name=coin_id, price_usd=coin_data["usd"],
                change_24h_pct=coin_data.get("usd_24h_change"),
                last_updated=_format_timestamp(coin_data.get("last_updated_at")),
            )
        except KeyError as e:
            raise CryptoInvalidResponseError(f"CoinGecko response missing expected fields: {e}") from e
        self._cache.set(cache_key, price)
        return price

    async def get_market(self, symbol: str) -> CryptoMarket:
        coin_id = _resolve_id(symbol)
        cache_key = f"market:{coin_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"vs_currency": "usd", "ids": coin_id}
        data = await self._get_with_retries("/coins/markets", params)
        if not data:
            raise CryptoNotFoundError(f"Непознат крипто символ: {symbol}")
        market = _market_from_payload(data[0])
        self._cache.set(cache_key, market)
        return market

    async def get_top_coins(self, limit: int = 10) -> List[CryptoMarket]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        cache_key = f"top:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": limit, "page": 1}
        data = await self._get_with_retries("/coins/markets", params)
        markets = [_market_from_payload(item) for item in data]
        self._cache.set(cache_key, markets)
        return markets

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
                last_error = CryptoTimeoutError(f"CoinGecko request timed out: {e}")
            except httpx.TransportError as e:
                last_error = CryptoConnectionError(f"CoinGecko connection failed: {e}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise CryptoInvalidResponseError(f"CoinGecko returned non-JSON response: {e}") from e
                if response.status_code == 429:
                    last_error = CryptoRateLimitError("CoinGecko rate limit exceeded")
                elif response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = CryptoError(f"CoinGecko server error (HTTP {response.status_code})")
                else:
                    raise CryptoError(f"CoinGecko request failed (HTTP {response.status_code}): {response.text}")
            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug("CoinGecko request failed, retrying", attempt=attempt, max_retries=self.max_retries, backoff_seconds=backoff)
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error

    async def __aenter__(self) -> "CoinGeckoProvider":
        return self

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        await self.close()
