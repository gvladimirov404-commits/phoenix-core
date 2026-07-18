"""Unit tests for phoenix_core.ai.groq_provider.GroqProvider.

All HTTP calls are mocked — no real network requests are made.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from phoenix_core.ai.groq_provider import GroqProvider
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderInvalidResponseError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)


def make_provider(api_key: str = "gsk-test", max_retries: int = 0) -> GroqProvider:
    return GroqProvider(api_key=api_key, max_retries=max_retries)


def fake_response(status_code: int, json_data: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


class TestConstruction:
    def test_defaults_to_groq_base_url_and_model(self) -> None:
        provider = GroqProvider(api_key="gsk-test")
        assert provider.base_url == "https://api.groq.com/openai/v1"
        assert provider.model == "llama-3.3-70b-versatile"
        assert provider.name == "groq"

    def test_base_url_and_model_are_overridable(self) -> None:
        provider = GroqProvider(api_key="gsk-test", base_url="https://custom.example/v1", model="custom-model")
        assert provider.base_url == "https://custom.example/v1"
        assert provider.model == "custom-model"


class TestChatSuccess:
    async def test_returns_standardized_ai_response(self, monkeypatch) -> None:
        provider = make_provider()
        ok_response = fake_response(
            200,
            {
                "choices": [{"message": {"content": "hello there"}, "finish_reason": "stop"}],
                "model": "llama-3.3-70b-versatile",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )
        mock_post = AsyncMock(return_value=ok_response)
        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

        assert result.content == "hello there"
        assert result.provider == "groq"
        assert result.usage["total_tokens"] == 5
        mock_post.assert_awaited_once()

    async def test_sends_openai_compatible_payload_to_chat_completions(self, monkeypatch) -> None:
        provider = make_provider()
        ok_response = fake_response(
            200,
            {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "model": "llama-3.3-70b-versatile"},
        )
        mock_post = AsyncMock(return_value=ok_response)
        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        await provider.chat(messages=[{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=100)

        args, kwargs = mock_post.call_args
        assert args[0] == "/chat/completions"
        payload = kwargs["json"]
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["messages"] == [{"role": "user", "content": "hi"}]
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 100
        assert payload["stream"] is False


class TestChatErrors:
    async def test_missing_api_key_raises_ai_provider_error(self) -> None:
        provider = GroqProvider(api_key="")
        with pytest.raises(AIProviderError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_401_raises_ai_provider_error(self, monkeypatch) -> None:
        provider = make_provider()
        response = fake_response(401, {"error": {"message": "invalid api key"}})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        with pytest.raises(AIProviderError, match="authentication failed"):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_403_raises_ai_provider_error(self, monkeypatch) -> None:
        provider = make_provider()
        response = fake_response(403, {"error": {"message": "forbidden"}})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        with pytest.raises(AIProviderError, match="forbidden"):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_404_raises_ai_provider_error(self, monkeypatch) -> None:
        provider = make_provider()
        response = fake_response(404, {"error": {"message": "not found"}})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        with pytest.raises(AIProviderError, match="endpoint not found"):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_429_raises_rate_limit_error(self, monkeypatch) -> None:
        provider = make_provider()
        response = fake_response(429, {"error": {"message": "rate limited"}})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        with pytest.raises(AIProviderRateLimitError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_5xx_exhausts_retries_and_raises_ai_provider_error(self, monkeypatch) -> None:
        provider = GroqProvider(api_key="gsk-test", max_retries=1)
        response = fake_response(500, {"error": {"message": "server error"}})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        monkeypatch.setattr("phoenix_core.ai.groq_provider.asyncio.sleep", AsyncMock())
        with pytest.raises(AIProviderError, match="server error"):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_malformed_response_raises_invalid_response_error(self, monkeypatch) -> None:
        provider = make_provider()
        response = fake_response(200, {"unexpected": "shape"})
        monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
        with pytest.raises(AIProviderInvalidResponseError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_timeout_raises_ai_provider_timeout_error(self, monkeypatch) -> None:
        provider = make_provider(max_retries=0)
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        with pytest.raises(AIProviderTimeoutError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_connection_error_raises_ai_provider_connection_error(self, monkeypatch) -> None:
        provider = make_provider(max_retries=0)
        mock_post = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        with pytest.raises(AIProviderConnectionError):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])


class TestHealthCheck:
    async def test_configured_when_api_key_present(self) -> None:
        provider = make_provider(api_key="gsk-test")
        result = await provider.health_check()
        assert result["status"] == "configured"
        assert result["provider"] == "groq"

    async def test_misconfigured_when_api_key_missing(self) -> None:
        provider = GroqProvider(api_key="")
        result = await provider.health_check()
        assert result["status"] == "misconfigured"
        assert "api_key is not set" in result["issues"]

    async def test_health_check_makes_no_network_call(self, monkeypatch) -> None:
        provider = make_provider()
        mock_post = AsyncMock()
        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        await provider.health_check()
        mock_post.assert_not_awaited()


class TestClose:
    async def test_close_is_safe_when_no_client_was_created(self) -> None:
        provider = make_provider()
        await provider.close()  # should not raise
