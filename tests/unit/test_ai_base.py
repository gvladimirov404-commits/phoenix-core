"""Unit tests for phoenix_core.ai.base (AIResponse, BaseAIProvider contract)."""
from phoenix_core.ai.base import AIResponse


def test_ai_response_to_dict_contains_all_fields() -> None:
    response = AIResponse(
        content="hello",
        provider="mock",
        model="mock-model",
        usage={"total_tokens": 3},
        metadata={"finish_reason": "stop"},
    )
    data = response.to_dict()
    assert data["content"] == "hello"
    assert data["provider"] == "mock"
    assert data["model"] == "mock-model"
    assert data["usage"] == {"total_tokens": 3}
    assert data["metadata"] == {"finish_reason": "stop"}


def test_ai_response_defaults_usage_and_metadata_to_empty_dict() -> None:
    response = AIResponse(content="hi", provider="mock", model="m")
    assert response.usage == {}
    assert response.metadata == {}


def test_validate_model_returns_requested_model_if_available(mock_provider) -> None:
    assert mock_provider.validate_model("mock-model") == "mock-model"


def test_validate_model_falls_back_to_default_if_unavailable(mock_provider) -> None:
    assert mock_provider.validate_model("unknown-model") == mock_provider.model


def test_validate_model_falls_back_to_default_if_none(mock_provider) -> None:
    assert mock_provider.validate_model(None) == mock_provider.model
