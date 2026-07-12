"""
AIGuard — AI Guard Layer facade (Task 011).

The single entrypoint phoenix_core.telegram.commands.cmd_ask talks to.
Composes the four independent Guard components (RateLimiter, CostGuard,
RetryPolicy, OutputSanitizer) behind one object so callers don't need to
know about, resolve, or sequence each one individually. AIGuard itself
contains no AI-provider-specific logic and never imports AIRouter or any
provider — it only ever receives an already-built coroutine factory to
run (see call_provider), exactly like Task 010's ContextBuilder has no
idea AIRouter exists.

Runs strictly *before* (guard_request) and *around*/*after*
(call_provider, sanitize_output) a provider call — it never calls a
provider itself and never touches Conversation Memory.
"""
from typing import Any, Awaitable, Callable, Dict, List, TypeVar

from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.guard.rate_limiter import RateLimiter
from phoenix_core.guard.retry import RetryPolicy
from phoenix_core.guard.sanitizer import OutputSanitizer

T = TypeVar("T")


class AIGuard:
    """Facade composing rate limiting, cost guarding, retry, and output sanitization."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        cost_guard: CostGuard,
        retry_policy: RetryPolicy,
        sanitizer: OutputSanitizer,
    ) -> None:
        """Create the guard facade from its four already-configured components."""
        self._rate_limiter = rate_limiter
        self._cost_guard = cost_guard
        self._retry_policy = retry_policy
        self._sanitizer = sanitizer

    def guard_request(self, user_id: int, prompt: str, messages: List[Dict[str, str]]) -> None:
        """Run every pre-request check, in order, before a provider is ever called.

        Order: rate limit first (cheapest, most likely to reject abusive
        callers), then prompt size, then assembled context size.

        Raises:
            RateLimitExceededError, PromptTooLargeError, ContextTooLargeError
        """
        self._rate_limiter.check(user_id)
        self._cost_guard.check_prompt(prompt)
        self._cost_guard.check_context(messages)

    async def call_provider(self, coro_factory: Callable[[], Awaitable[T]]) -> T:
        """Run a provider call through the centralized retry policy."""
        return await self._retry_policy.run(coro_factory)

    def sanitize_output(self, text: str) -> str:
        """Sanitize AI-generated text before it is sent to Telegram."""
        return self._sanitizer.sanitize(text)

    async def health_check(self) -> Dict[str, Any]:
        """Aggregate health/config from every Guard component, for /health and /status."""
        return {
            "status": "healthy",
            "rate_limiter": await self._rate_limiter.health_check(),
            "cost_guard": await self._cost_guard.health_check(),
            "retry_policy": await self._retry_policy.health_check(),
            "sanitizer": await self._sanitizer.health_check(),
        }
