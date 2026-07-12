"""
DeepSeek AI provider — the single real provider for the V1 AI foundation.

Implements phoenix_core.ai.base.BaseAIProvider against DeepSeek's
OpenAI-compatible chat completions API. No other providers are
implemented at this stage (see Task 003 scope).
"""
import asyncio
import json
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional, Type

import httpx

from phoenix_core.ai.base import AIResponse, BaseAIProvider
from phoenix_core.utils.exceptions import (
    AIProviderConnectionError,
    AIProviderError,
    AIProviderInvalidResponseError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
)
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# Known DeepSeek chat models at time of writing. Not fetched dynamically —
# dynamic model discovery is out of scope for the V1 single-provider MVP.
_AVAILABLE_MODELS = ["deepseek-chat", "deepseek-reasoner"]

# Retries only make sense for transient failures, not for auth/client errors.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class DeepSeekProvider(BaseAIProvider):
    """DeepSeek chat completion provider (OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Create a DeepSeek provider instance.

        Args:
            api_key: DeepSeek API key.
            model: Default model (defaults to "deepseek-chat").
            base_url: Override for DeepSeek's API base URL.
            timeout: Request timeout in seconds.
            max_retries: Max retry attempts for transient (5xx) failures.
        """
        super().__init__(
            api_key=api_key,
            model=model or DEFAULT_MODEL,
            base_url=base_url or DEFAULT_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def name(self) -> str:
        """Provider identifier used in AIResponse.provider and router logging."""
        return "deepseek"

    @property
    def available_models(self) -> List[str]:
        """Known DeepSeek chat models (not fetched dynamically — see module docstring)."""
        return list(_AVAILABLE_MODELS)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client, if one was created."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Send a non-streaming chat completion request to DeepSeek (with retries)."""
        resolved_model = self.validate_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = await self._post_with_retries("/chat/completions", payload)

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AIProviderInvalidResponseError(
                f"DeepSeek response missing expected fields: {e}"
            ) from e

        usage = data.get("usage", {}) or {}
        return AIResponse(
            content=content,
            provider=self.name,
            model=data.get("model", resolved_model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            metadata={"finish_reason": choice.get("finish_reason")},
        )

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response from DeepSeek as SSE `data:` chunks."""
        resolved_model = self.validate_model(model)
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        client = self._get_client()
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code != 200:
                    await response.aread()
                    await self._raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:"):].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        event = json.loads(chunk)
                        delta = event["choices"][0]["delta"].get("content")
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield delta
        except httpx.TimeoutException as e:
            raise AIProviderTimeoutError(f"DeepSeek streaming request timed out: {e}") from e
        except httpx.TransportError as e:
            raise AIProviderConnectionError(f"DeepSeek streaming connection failed: {e}") from e

    async def health_check(self) -> Dict[str, Any]:
        """Validate local configuration only — no network request is made."""
        issues = []
        if not self.api_key:
            issues.append("api_key is not set")
        if not self.base_url:
            issues.append("base_url is not set")
        if not self.model:
            issues.append("model is not set")

        return {
            "status": "configured" if not issues else "misconfigured",
            "provider": self.name,
            "model": self.model,
            "issues": issues,
        }

    async def _post_with_retries(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise AIProviderError("DeepSeek API key is not configured")

        client = self._get_client()
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self.max_retries:
            try:
                response = await client.post(path, json=payload)
            except httpx.TimeoutException as e:
                last_error = AIProviderTimeoutError(f"DeepSeek request timed out: {e}")
            except httpx.TransportError as e:
                last_error = AIProviderConnectionError(f"DeepSeek connection failed: {e}")
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as e:
                        raise AIProviderInvalidResponseError(
                            f"DeepSeek returned non-JSON response: {e}"
                        ) from e
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = AIProviderError(
                        f"DeepSeek server error (HTTP {response.status_code})"
                    )
                else:
                    await self._raise_for_status(response)

            attempt += 1
            if attempt <= self.max_retries:
                backoff = min(2 ** attempt * 0.5, 8.0)
                logger.debug(
                    "DeepSeek request failed, retrying",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        raise last_error

    async def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise the appropriate standardized exception for a non-200 response."""
        status = response.status_code
        try:
            body = response.json()
            message = body.get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text

        if status in (401, 403):
            raise AIProviderError(f"DeepSeek authentication failed (HTTP {status}): {message}")
        if status == 429:
            raise AIProviderRateLimitError(f"DeepSeek rate limit exceeded: {message}")
        if status == 400:
            raise AIProviderInvalidResponseError(f"DeepSeek rejected the request (HTTP 400): {message}")
        raise AIProviderError(f"DeepSeek request failed (HTTP {status}): {message}")

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Close the underlying HTTP client."""
        await self.close()
