"""
Abstract base class for AI providers.
Implements the Strategy pattern for interchangeable AI providers.
"""
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional, Type

import httpx

from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class AIResponse:
    """Standardized AI response object"""
    def __init__(
        self,
        content: str,
        provider: str,
        model: str,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Create a standardized response returned by every AI provider.

        Args:
            content: The generated text.
            provider: Name of the provider that produced the response (e.g. "deepseek").
            model: Name of the model that produced the response.
            usage: Optional token usage counters (e.g. prompt/completion/total tokens).
            metadata: Optional provider-specific extra information.
        """
        self.content = content
        self.provider = provider
        self.model = model
        self.usage = usage or {}
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation of this response."""
        return {
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "usage": self.usage,
            "metadata": self.metadata,
        }


class BaseAIProvider(ABC):
    """Abstract base class for AI providers"""
    def __init__(
        self,
        api_key: str,
        model: str = "default",
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Store common provider configuration.

        Args:
            api_key: Provider API key/credential.
            model: Default model to use when a request doesn't specify one.
            base_url: Optional override for the provider's API base URL.
            timeout: Request timeout in seconds.
            max_retries: Max retry attempts for transient failures.
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass

    @property
    @abstractmethod
    def available_models(self) -> List[str]:
        """List of available models"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Send a chat completion request"""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check provider health status"""
        pass

    def validate_model(self, model: Optional[str]) -> str:
        """Validate and return the model name"""
        if model and model in self.available_models:
            return model
        return self.model

    async def __aenter__(self) -> "BaseAIProvider":
        """Enable `async with SomeProvider(...) as provider:` usage."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Close the underlying HTTP client, if one was created."""
        if self._client:
            await self._client.aclose()
