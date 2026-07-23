"""Unit tests for CoinGeckoProvider. All HTTP calls mocked."""
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
from phoenix_core.services.crypto.coingecko_provider import CoinGeckoProvider
from phoenix_core.utils.exceptions import (
    CryptoConnectionError, CryptoError, CryptoNotFoundError, CryptoRateLimitError, CryptoTimeoutError,
)


def make_provider(max_retries: int = 0, cache_ttl_seconds: float = 60.0) -> CoinGeckoProvider:
    return CoinGeckoProvider(max_retries=max_retries, cache_ttl_seconds=cache_ttl_seconds)


def fake_response(status_code: int, json_data) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


class TestConstruction:
    def test_defaults_to_coingecko_base_url(self) -> None:
        provider = CoinGeckoProvider()
        assert provider.base_url == "https://api.coingecko.com/api/v3"
        assert provider.name == "coingecko"


class TestGetPrice:
    async def test_returns_price_for_known_symbol(self, monkeypatch) -> None:
        provider = make_provider()
        ok = fake_response(200, {"bitcoin": {"usd": 65000.5, "usd_24h_change": 2.31, "last_updated_at": 1700000000}})
        mock_get = AsyncMock(return_value=ok)
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        result = await provider.get_price("btc")
        assert result.symbol == "BTC"
        assert result.price_usd == 65000.5
        mock_get.assert_awaited_once()

    async def test_resolves_ticker_to_coingecko_id(self, monkeypatch) -> None:
        provider = make_provider()
        mock_get = AsyncMock(return_value=fake_response(200, {"bitcoin": {"usd": 100.0}}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        await provider.get_price("BTC")
        args, kwargs = mock_get.call_args
        assert kwargs["params"]["ids"] == "bitcoin"

    async def test_unknown_symbol_raises_not_found(self, monkeypatch) -> None:
        provider = make_provider()
        mock_get = AsyncMock(return_value=fake_response(200, {}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoNotFoundError):
            await provider.get_price("notarealcoin")


class TestGetMarket:
    async def test_returns_full_market_data(self, monkeypatch) -> None:
        provider = make_provider()
        ok = fake_response(200, [{
            "symbol": "btc", "name": "Bitcoin", "current_price": 65000.5,
            "price_change_percentage_24h": 2.31, "market_cap": 1_200_000_000_000,
            "total_volume": 30_000_000_000, "last_updated": "2026-07-23T00:00:00.000Z", "market_cap_rank": 1,
        }])
        mock_get = AsyncMock(return_value=ok)
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        result = await provider.get_market("btc")
        assert result.symbol == "BTC"
        assert result.name == "Bitcoin"
        assert result.market_cap_usd == 1_200_000_000_000

    async def test_empty_result_raises_not_found(self, monkeypatch) -> None:
        provider = make_provider()
        mock_get = AsyncMock(return_value=fake_response(200, []))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoNotFoundError):
            await provider.get_market("notarealcoin")


class TestGetTopCoins:
    async def test_returns_list_of_markets(self, monkeypatch) -> None:
        provider = make_provider()
        ok = fake_response(200, [
            {"symbol": "btc", "name": "Bitcoin", "current_price": 65000.0, "price_change_percentage_24h": 1.0,
             "market_cap": 1_000_000_000_000, "total_volume": 10_000_000_000, "last_updated": "now", "market_cap_rank": 1},
            {"symbol": "eth", "name": "Ethereum", "current_price": 3500.0, "price_change_percentage_24h": -0.5,
             "market_cap": 400_000_000_000, "total_volume": 5_000_000_000, "last_updated": "now", "market_cap_rank": 2},
        ])
        mock_get = AsyncMock(return_value=ok)
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        result = await provider.get_top_coins(limit=2)
        assert len(result) == 2
        assert result[0].symbol == "BTC"

    async def test_invalid_limit_raises_value_error(self) -> None:
        provider = make_provider()
        with pytest.raises(ValueError):
            await provider.get_top_coins(limit=0)


class TestCaching:
    async def test_repeated_call_within_ttl_does_not_hit_network_again(self, monkeypatch) -> None:
        provider = make_provider(cache_ttl_seconds=60.0)
        mock_get = AsyncMock(return_value=fake_response(200, {"bitcoin": {"usd": 100.0}}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        first = await provider.get_price("btc")
        second = await provider.get_price("btc")
        assert first == second
        mock_get.assert_awaited_once()


class TestErrorHandling:
    async def test_timeout_raises_crypto_timeout_error(self, monkeypatch) -> None:
        provider = make_provider(max_retries=0)
        mock_get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoTimeoutError):
            await provider.get_price("btc")

    async def test_connection_error_raises_crypto_connection_error(self, monkeypatch) -> None:
        provider = make_provider(max_retries=0)
        mock_get = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoConnectionError):
            await provider.get_price("btc")

    async def test_rate_limit_status_raises_crypto_rate_limit_error(self, monkeypatch) -> None:
        provider = make_provider(max_retries=0)
        mock_get = AsyncMock(return_value=fake_response(429, {}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoRateLimitError):
            await provider.get_price("btc")

    async def test_server_error_retries_then_raises(self, monkeypatch) -> None:
        provider = make_provider(max_retries=1)
        mock_get = AsyncMock(return_value=fake_response(500, {}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        with pytest.raises(CryptoError):
            await provider.get_price("btc")
        assert mock_get.await_count == 2

    async def test_client_error_raises_immediately_without_retry(self, monkeypatch) -> None:
        provider = make_provider(max_retries=3)
        mock_get = AsyncMock(return_value=fake_response(400, {}))
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        with pytest.raises(CryptoError):
            await provider.get_price("btc")
        mock_get.assert_awaited_once()


class TestHealthCheck:
    async def test_reports_configured_status_without_network_call(self, monkeypatch) -> None:
        provider = make_provider()
        mock_get = AsyncMock()
        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        health = await provider.health_check()
        assert health["status"] == "configured"
        mock_get.assert_not_awaited()
