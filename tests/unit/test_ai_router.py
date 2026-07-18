"""Unit tests for phoenix_core.ai.router.AIRouter (multi-provider: DeepSeek + Groq)."""
import pytest

from phoenix_core.ai.router import AIRouter
from phoenix_core.utils.exceptions import (
    AIProviderNotFoundError,
    ConfigurationError,
    ValidationError,
)

from .conftest import MockAIProvider


def make_router_with_mock(name: str = "mock", default_provider: str = "mock") -> AIRouter:
    """Build an AIRouter with no configured providers, then inject a mock directly
    via the public register_provider() method (no real API key/network needed)."""
    router = AIRouter(providers=[], default_provider=default_provider)
    router.register_provider(name, MockAIProvider())
    return router


class TestGetProvider:
    def test_raises_configuration_error_when_nothing_registered(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        with pytest.raises(ConfigurationError):
            router.get_provider()

    def test_resolves_default_provider_when_no_name_given(self) -> None:
        router = make_router_with_mock()
        provider = router.get_provider()
        assert provider.name == "mock"

    def test_raises_not_found_for_unknown_provider_name(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(AIProviderNotFoundError):
            router.get_provider("does-not-exist")


class TestChatValidation:
    async def test_rejects_empty_messages(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(ValidationError):
            await router.chat(messages=[])

    async def test_rejects_message_missing_content(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(ValidationError):
            await router.chat(messages=[{"role": "user"}])

    async def test_rejects_non_string_content(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(ValidationError):
            await router.chat(messages=[{"role": "user", "content": 123}])

    async def test_rejects_blank_content(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(ValidationError):
            await router.chat(messages=[{"role": "user", "content": "   "}])


class TestChat:
    async def test_returns_standardized_response(self) -> None:
        router = make_router_with_mock()
        result = await router.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.provider == "mock"
        assert result.content == "mock response"
        assert result.usage["total_tokens"] == 10

    async def test_propagates_provider_errors(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(should_fail=RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            await router.chat(messages=[{"role": "user", "content": "hi"}])


class TestStreamChat:
    async def test_yields_chunks_from_provider(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        router.register_provider("mock", MockAIProvider(response_content="a b c"))
        chunks = [c async for c in router.stream_chat(messages=[{"role": "user", "content": "hi"}])]
        assert "".join(chunks).strip() == "a b c"

    async def test_validates_input_before_streaming(self) -> None:
        router = make_router_with_mock()
        with pytest.raises(ValidationError):
            async for _ in router.stream_chat(messages=[]):
                pass


class TestProviderSelection:
    def test_list_providers_returns_registered_names(self) -> None:
        router = make_router_with_mock(name="mock")
        assert router.list_providers() == ["mock"]

    def test_list_providers_empty_when_none_registered(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        assert router.list_providers() == []

    def test_is_provider_available_true_for_default(self) -> None:
        router = make_router_with_mock(name="mock", default_provider="mock")
        assert router.is_provider_available() is True

    def test_is_provider_available_false_when_not_registered(self) -> None:
        router = make_router_with_mock(name="mock")
        assert router.is_provider_available("does-not-exist") is False

    def test_is_provider_available_false_when_nothing_configured(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        assert router.is_provider_available() is False


class TestHealthCheck:
    async def test_not_configured_when_no_providers(self) -> None:
        router = AIRouter(providers=[], default_provider="mock")
        result = await router.health_check()
        assert result["status"] == "not_configured"

    async def test_healthy_when_provider_configured(self) -> None:
        router = make_router_with_mock()
        result = await router.health_check()
        assert result["status"] == "healthy"
        assert "mock" in result["providers"]


class TestMultiProviderConstruction:
    """Task 014: AIRouter builds real DeepSeek/Groq provider instances from AIProviderConfig."""

    def test_builds_a_groq_provider_from_config(self) -> None:
        from pydantic import SecretStr

        from phoenix_core.ai.groq_provider import GroqProvider
        from phoenix_core.config.settings import AIProviderConfig

        config = AIProviderConfig(name="groq", api_key=SecretStr("gsk-test"), model="llama-3.3-70b-versatile")
        router = AIRouter(providers=[config], default_provider="groq")

        provider = router.get_provider("groq")
        assert isinstance(provider, GroqProvider)
        assert provider.name == "groq"

    def test_builds_both_deepseek_and_groq_when_both_configured(self) -> None:
        from pydantic import SecretStr

        from phoenix_core.ai.deepseek_provider import DeepSeekProvider
        from phoenix_core.ai.groq_provider import GroqProvider
        from phoenix_core.config.settings import AIProviderConfig

        configs = [
            AIProviderConfig(name="deepseek", api_key=SecretStr("sk-test")),
            AIProviderConfig(name="groq", api_key=SecretStr("gsk-test")),
        ]
        router = AIRouter(providers=configs, default_provider="groq")

        assert isinstance(router.get_provider("deepseek"), DeepSeekProvider)
        assert isinstance(router.get_provider("groq"), GroqProvider)
        assert isinstance(router.get_provider(), GroqProvider)  # default_provider="groq"
        assert set(router.list_providers()) == {"deepseek", "groq"}

    def test_switching_default_provider_to_groq_changes_nothing_else(self) -> None:
        """AI_DEFAULT_PROVIDER=groq must not require any other config change (Task 014 acceptance criterion)."""
        from pydantic import SecretStr

        from phoenix_core.config.settings import AIProviderConfig

        config = AIProviderConfig(name="groq", api_key=SecretStr("gsk-test"))
        router = AIRouter(providers=[config], default_provider="groq")

        assert router.is_provider_available() is True
        assert router.get_provider().name == "groq"
