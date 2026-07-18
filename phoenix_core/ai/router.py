"""
AI provider router.

Accepts a chat request, validates input, resolves the configured
provider (DeepSeek or Groq — see _PROVIDER_CLASSES), and returns a
standardized AIResponse. Fallback, load balancing, and cost optimization
are explicitly out of scope (see Task 003; Task 014 added the second
provider without changing anything else in this file).
"""
from typing import Any, AsyncIterator, Dict, List, Optional, Type
from uuid import uuid4

from phoenix_core.ai.base import AIResponse, BaseAIProvider
from phoenix_core.ai.deepseek_provider import DeepSeekProvider
from phoenix_core.ai.groq_provider import GroqProvider
from phoenix_core.config.settings import AIProviderConfig
from phoenix_core.utils.exceptions import ConfigurationError, AIProviderNotFoundError, ValidationError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

# Maps a configured provider name to its concrete implementation.
# "deepseek" and "groq" are implemented (Task 003, Task 014) — both are
# OpenAI-compatible chat completions APIs, so adding a new one here is the
# only router change a future provider needs (see AIRouter.register_provider).
_PROVIDER_CLASSES: Dict[str, Type[BaseAIProvider]] = {
    "deepseek": DeepSeekProvider,
    "groq": GroqProvider,
}


class AIRouter:
    """Routes chat requests to the single configured AI provider."""

    def __init__(self, providers: List[AIProviderConfig], default_provider: str):
        """Build the router and eagerly construct all enabled, supported providers.

        Args:
            providers: Provider configurations (from Settings.ai_providers).
            default_provider: Name of the provider to use when none is specified.
        """
        self.provider_configs = providers
        self.default_provider = default_provider
        self._registered_providers: Dict[str, BaseAIProvider] = {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        for config in self.provider_configs:
            if not config.enabled:
                continue
            provider_class = _PROVIDER_CLASSES.get(config.name)
            if provider_class is None:
                logger.warning(
                    "Skipping unsupported AI provider in configuration",
                    provider=config.name,
                )
                continue
            self._registered_providers[config.name] = provider_class(
                api_key=config.api_key.get_secret_value(),
                model=config.model,
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
            )

        logger.info(
            "AIRouter initialized",
            configured_providers=list(self._registered_providers.keys()),
            default_provider=self.default_provider,
        )

    def register_provider(self, name: str, provider: BaseAIProvider) -> None:
        """Register a provider instance directly (used by tests and future providers)."""
        self._registered_providers[name] = provider

    def list_providers(self) -> List[str]:
        """Return the names of all currently registered (configured) providers."""
        return list(self._registered_providers.keys())

    def is_provider_available(self, name: Optional[str] = None) -> bool:
        """Check whether the given provider (or the default provider) is registered."""
        resolved_name = name or self.default_provider
        return resolved_name in self._registered_providers

    def get_provider(self, name: Optional[str] = None) -> BaseAIProvider:
        """Resolve a provider by name, or the default provider if no name is given."""
        if not self._registered_providers:
            raise ConfigurationError(
                "No AI provider is configured. Set the required environment "
                "variables for at least one supported provider (e.g. "
                "PHOENIX_AI_DEEPSEEK_API_KEY or GROQ_API_KEY)."
            )

        resolved_name = name or self.default_provider
        provider = self._registered_providers.get(resolved_name)
        if provider is None:
            raise AIProviderNotFoundError(
                f"AI provider '{resolved_name}' is not configured or not supported. "
                f"Configured providers: {list(self._registered_providers.keys())}"
            )
        return provider

    @staticmethod
    def _validate_messages(messages: List[Dict[str, str]]) -> None:
        if not messages or not isinstance(messages, list):
            raise ValidationError("messages must be a non-empty list")
        for entry in messages:
            if not isinstance(entry, dict) or "role" not in entry or "content" not in entry:
                raise ValidationError(
                    "each message must be a dict with 'role' and 'content' keys"
                )
            if not isinstance(entry["content"], str) or not entry["content"].strip():
                raise ValidationError("message 'content' must be a non-empty string")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Validate input, call the configured provider, and return a standardized result."""
        self._validate_messages(messages)
        resolved_provider = self.get_provider(provider)
        request_id = uuid4().hex[:8]

        logger.info(
            "AI provider selected",
            request_id=request_id,
            provider=resolved_provider.name,
            default=provider is None,
        )
        logger.info(
            "AI chat request started",
            request_id=request_id,
            provider=resolved_provider.name,
            model=model or resolved_provider.model,
            message_count=len(messages),
        )
        try:
            response = await resolved_provider.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as e:
            logger.error(
                "AI provider failed",
                request_id=request_id,
                provider=resolved_provider.name,
                error_type=type(e).__name__,
            )
            raise

        logger.info(
            "AI chat request completed",
            request_id=request_id,
            provider=response.provider,
            model=response.model,
            total_tokens=response.usage.get("total_tokens", 0),
        )
        return response

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Validate input, call the configured provider, and stream the response."""
        self._validate_messages(messages)
        resolved_provider = self.get_provider(provider)
        request_id = uuid4().hex[:8]

        logger.info(
            "AI provider selected",
            request_id=request_id,
            provider=resolved_provider.name,
            default=provider is None,
        )
        logger.info(
            "AI streaming chat request started",
            request_id=request_id,
            provider=resolved_provider.name,
            model=model or resolved_provider.model,
            message_count=len(messages),
        )
        try:
            async for chunk in resolved_provider.stream_chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield chunk
        except Exception as e:
            logger.error(
                "AI provider failed",
                request_id=request_id,
                provider=resolved_provider.name,
                error_type=type(e).__name__,
            )
            raise

    async def start(self) -> None:
        """Lifecycle no-op — providers are lazily connected on first request."""
        logger.debug(
            "AIRouter.start() called",
            configured_providers=list(self._registered_providers.keys()),
        )

    async def stop(self) -> None:
        """Close any open provider HTTP clients."""
        for provider in self._registered_providers.values():
            close = getattr(provider, "close", None)
            if callable(close):
                await close()
        logger.debug("AIRouter.stop() called")

    async def health_check(self) -> Dict[str, Any]:
        """Validate local configuration for all registered providers (no network calls)."""
        if not self._registered_providers:
            return {
                "status": "not_configured",
                "detail": "No AI provider is configured",
                "providers": {},
            }

        provider_health: Dict[str, Any] = {}
        overall_ok = True
        for name, provider in self._registered_providers.items():
            result = await provider.health_check()
            provider_health[name] = result
            if result.get("status") != "configured":
                overall_ok = False

        return {
            "status": "healthy" if overall_ok else "misconfigured",
            "default_provider": self.default_provider,
            "providers": provider_health,
        }
