"""
RetryPolicy — centralized, bounded retry with exponential backoff (Task 011).

Wraps a single AIRouter.chat() call (or anything else with the same
`() -> Awaitable[T]` shape) and retries it only for the exception types
explicitly marked retryable — by default `AIProviderTimeoutError` and
`AIProviderConnectionError`, i.e. exactly "timeout" and "connection error"
from Task 011, Задача 4. Every other exception (including
`AIProviderNotFoundError`, `ConfigurationError`, `ValidationError`, and
the generic `AIProviderError` DeepSeekProvider also uses for
authentication failures — see module note below) propagates immediately,
matching "Не retry-вай: authentication; invalid request; validation
errors."

Note on "transient provider error": DeepSeekProvider
(phoenix_core/ai/deepseek_provider.py) already retries 5xx HTTP responses
internally with its own exponential backoff before ever raising — by the
time a plain `AIProviderError` reaches this policy, it has either already
exhausted the provider's own retries or is DeepSeek's shared exception
class for authentication failures (401/403) and other non-timeout,
non-connection HTTP errors, which are not safely distinguishable from
here. This policy deliberately does NOT retry the generic
`AIProviderError` to avoid retrying what may be an auth failure — see the
Task 011 final report for this trade-off and a Task 012 recommendation.

This is a general-purpose retry helper: it has no AIRouter- or
AI-specific logic beyond its default retryable exception tuple, which
callers can override.
"""
import asyncio
from typing import Any, Awaitable, Callable, Dict, Tuple, Type, TypeVar

from phoenix_core.utils.exceptions import AIProviderConnectionError, AIProviderTimeoutError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 2
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0
DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    AIProviderTimeoutError,
    AIProviderConnectionError,
)


class RetryPolicy:
    """Runs an async callable with bounded retry + exponential backoff on transient errors."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        retryable_exceptions: Tuple[Type[BaseException], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
    ) -> None:
        """Create a retry policy.

        Args:
            max_retries: Max number of *additional* attempts after the first.
                0 disables retrying (the call is made exactly once).
            base_delay: Backoff delay before the first retry, in seconds.
            max_delay: Backoff delay ceiling, in seconds.
            retryable_exceptions: Exception types that trigger a retry;
                anything else propagates immediately.
        """
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retryable_exceptions = retryable_exceptions

    async def run(self, coro_factory: Callable[[], Awaitable[T]]) -> T:
        """Call `coro_factory()` and await it, retrying on a retryable exception.

        `coro_factory` is a zero-argument callable returning a fresh
        awaitable each time (e.g. `lambda: ai_router.chat(messages=messages)`)
        — not an already-created coroutine, since a coroutine object can
        only be awaited once.
        """
        attempt = 0
        while True:
            try:
                result = await coro_factory()
            except self._retryable_exceptions as e:
                attempt += 1
                if attempt > self._max_retries:
                    logger.warning(
                        "AI request retry exhausted",
                        attempts=attempt - 1,
                        error_type=type(e).__name__,
                    )
                    raise
                backoff = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
                logger.info(
                    "AI request retry",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    backoff_seconds=backoff,
                    error_type=type(e).__name__,
                )
                await asyncio.sleep(backoff)
                continue
            else:
                if attempt > 0:
                    logger.info("AI request retry succeeded", attempt=attempt)
                return result

    async def health_check(self) -> Dict[str, Any]:
        """Report RetryPolicy's configured limits for the AI Guard health summary."""
        return {
            "max_retries": self._max_retries,
            "base_delay_seconds": self._base_delay,
            "max_delay_seconds": self._max_delay,
        }
