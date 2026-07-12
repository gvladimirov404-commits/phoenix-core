"""Shared fixtures and test doubles for unit tests."""
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from phoenix_core.ai.base import AIResponse, BaseAIProvider


class MockAIProvider(BaseAIProvider):
    """In-memory test double for BaseAIProvider. Makes no network calls."""

    def __init__(
        self,
        response_content: str = "mock response",
        should_fail: Optional[Exception] = None,
        api_key: str = "mock-key",
        model: str = "mock-model",
        **kwargs: Any,
    ):
        super().__init__(api_key=api_key, model=model, **kwargs)
        self._response_content = response_content
        self._should_fail = should_fail
        self.calls: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def available_models(self) -> List[str]:
        return ["mock-model"]

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AIResponse:
        self.calls.append({"messages": messages, "model": model})
        if self._should_fail:
            raise self._should_fail
        return AIResponse(
            content=self._response_content,
            provider=self.name,
            model=self.validate_model(model),
            usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        )

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._should_fail:
            raise self._should_fail
        for token in self._response_content.split():
            yield token + " "

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "configured", "provider": self.name}


@pytest.fixture
def mock_provider() -> MockAIProvider:
    return MockAIProvider()
