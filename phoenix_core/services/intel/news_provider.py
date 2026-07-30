"""NewsProvider — abstraction for crypto news feeds, plus CryptoPanicNewsProvider,
a free-tier (API-token-required) implementation backed by CryptoPanic (Task 020).

Mirrors phoenix_core.services.crypto.coingecko_provider.CoinGeckoProvider:
same httpx.AsyncClient + retry + TTLCache shape, same Crypto* exception
hierarchy (a news-fetch failure is still, conceptually, a crypto-data-
provider failure — reusing it avoids a parallel exception hierarchy for
one more read-only market-intelligence source).
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

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

DEFAULT_BASE_URL = "https://cryptopanic.com/api/v2"
DEFAULT_CACHE_TTL_SECONDS = 60.0
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

_SYMBOL_TO_CURRENCY = {
    "btc": "BTC", "eth": "ETH", "sol": "SOL", "bnb": "BNB", "xrp": "XRP",
    "ada": "ADA", "doge": "DOGE", "ton": "TON", "trx": "TRX", "dot": "DOT",
    "avax": "AVAX", "link": "LINK", "ltc": "LTC", "usdt": "USDT", "usdc": "USDC",
}


@dataclass
class NewsItem:
    title: str
    summary: str
    url: str
    published_at: Optional[str]
    source: Optional[str] = None


class NewsProvider(ABC):
    """Abstract base class for crypto news providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_news(self, symbol: str, limit: int = 5) -> List[NewsItem]: ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]: ...


def _resolve_currency(symbol: str) -> str:
    key = symbol.strip().lower()
    return _SYMBOL_TO_CURRENCY.get(key, symbol.strip().upper())


def _news_item_from_payload(item: Dict[str, Any]) -> NewsItem:
    try:
        title = item["title"]
        url = item["url"]
    except KeyError as e:
        raise CryptoInvalidResponseError(f"CryptoPanic response missing expected fields: {e}") from e

    source = (item.get("source") or {}).get("title")
    # CryptoPanic's free tier doesn't return a separate summary field —
    # the title is the closest thing available; kept as its own field so a
    # richer source could populate it later without changing NewsItem's shape.
    return NewsItem(
        title=title, summary=title, url=url,
        published_at=item.get("published_at") or item.get("created_at"), source=source,
    )


class CryptoPanicNewsProvider(NewsProvider):
    """CryptoPanic-backed NewsProvider. Requires a free CryptoPanic API token
    (PHOENIX_NEWS_API_TOKEN) — https://cryptopanic.com/developers/api/keys."""

    def __init__(
        self, api_token: str, base_url: Optional[str] = None, timeout: int = 15,
        max_retries: int = 2, cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.api_token = api_token
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    @property
    def name(self) -> str:
        return "cryptopanic"

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

    async def get_news(self, symbol: str, limit: int = 5) -> List[NewsItem]:
        currency = _resolve_currency(symbol)
        cache_key = f"news:{currency}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params = {"auth_token": self.api_token, "currencies": currency, "public": "true"}
        data = await self._get_with_retries("/posts/", params)
        results = data.get("results", [])
        items = [_news_item_from_payload(item) for item in results[:limit]]
        self._cache.set(cache_key, items)
        return items

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
                last_error = CryptoTimeoutError(f"CryptoPanic request timed out: {e}")
            except httpx.TransportError as e:
                last_error = CryptoConnectionError(f"CryptoPanic connection failed: {e}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise CryptoInvalidResponseError(f"CryptoPanic returned non-JSON response: {e}") from e
                if response.status_code == 429:
                    last_error = CryptoRateLimitError("CryptoPanic rate limit exceeded")
                elif response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = CryptoError(f"CryptoPanic server error (HTTP {response.status_code})")
                else:
                    raise CryptoError(f"CryptoPanic request failed (HTTP {response.status_code}): {response.text}")
            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug("CryptoPanic request failed, retrying", attempt=attempt, max_retries=self.max_retries, backoff_seconds=backoff)
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error

    async def __aenter__(self) -> "CryptoPanicNewsProvider":
        return self

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        await self.close()

import xml.etree.ElementTree as ET

# Reuse full names so a query for "btc" actually searches "bitcoin", which
# returns far more relevant results than the bare ticker.
_SYMBOL_TO_QUERY = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana", "bnb": "binance coin",
    "xrp": "ripple", "ada": "cardano", "doge": "dogecoin", "ton": "toncoin",
    "trx": "tron", "dot": "polkadot", "avax": "avalanche", "link": "chainlink",
    "ltc": "litecoin", "usdt": "tether", "usdc": "usd coin",
}


def _resolve_query(symbol: str) -> str:
    key = symbol.strip().lower()
    return _SYMBOL_TO_QUERY.get(key, symbol.strip())


class GoogleNewsRSSProvider(NewsProvider):
    """NewsProvider backed by Google News RSS search — free, keyless, no
    Cloudflare bot-protection issues (unlike CryptoPanicNewsProvider, kept
    above for reference/future use if that access issue is ever resolved).
    """

    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 2,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        """Create a Google News RSS-backed news provider.

        Args:
            timeout: Request timeout in seconds.
            max_retries: Max retry attempts for transient failures.
            cache_ttl_seconds: How long a cached response stays valid.
        """
        self.base_url = "https://news.google.com/rss/search"
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        self._cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    @property
    def name(self) -> str:
        """Provider identifier."""
        return "google-news-rss"

    def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client, if one was created."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def stop(self) -> None:
        """Lifecycle hook used by PhoenixApplication.stop()."""
        await self.close()

    async def get_news(self, symbol: str, limit: int = 5):
        """Return the latest `limit` news items for `symbol` (cached)."""
        query = _resolve_query(symbol)
        cache_key = f"news:{query}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        params = {"q": f"{query} crypto", "hl": "en-US", "gl": "US", "ceid": "US:en"}
        xml_text = await self._get_with_retries(params)
        items = _parse_rss(xml_text, limit)
        self._cache.set(cache_key, items)
        return items

    async def health_check(self):
        """Report configuration only — no network request is made."""
        return {"status": "configured", "provider": self.name, "cache_entries": len(self._cache)}

    async def _get_with_retries(self, params):
        client = self._get_client()
        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                response = await client.get(self.base_url, params=params)
            except httpx.TimeoutException as e:
                last_error = CryptoTimeoutError(f"Google News request timed out: {e}")
            except httpx.TransportError as e:
                last_error = CryptoConnectionError(f"Google News connection failed: {e}")
            else:
                if response.status_code == 200:
                    return response.text
                if response.status_code == 429:
                    last_error = CryptoRateLimitError("Google News rate limit exceeded")
                elif response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = CryptoError(f"Google News server error (HTTP {response.status_code})")
                else:
                    raise CryptoError(f"Google News request failed (HTTP {response.status_code})")

            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug(
                    "Google News request failed, retrying",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        raise last_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


def _parse_rss(xml_text: str, limit: int):
    """Parse a Google News RSS feed into NewsItem objects."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise CryptoInvalidResponseError(f"Google News returned invalid XML: {e}") from e

    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for item_el in channel.findall("item")[:limit]:
        title = item_el.findtext("title") or ""
        link = item_el.findtext("link") or ""
        pub_date = item_el.findtext("pubDate")
        source_el = item_el.find("source")
        source = source_el.text if source_el is not None else None
        items.append(NewsItem(title=title, summary=title, url=link, published_at=pub_date, source=source))
    return items

