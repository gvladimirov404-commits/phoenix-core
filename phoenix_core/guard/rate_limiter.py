"""
RateLimiter — per-user fixed-window request limiting (Task 011).

A small, storage-agnostic-by-design piece of the AI Guard Layer: it only
tracks *counts of requests per user within a time window* in memory,
nothing about request content. It does not call an AI provider, does not
know about AIRouter, and does not know about Conversation Memory — see
phoenix_core.guard.guard.AIGuard for how the pieces are composed.

Fixed-window algorithm (not sliding log): each user has a window that
starts on their first request and automatically resets once
`window_seconds` has elapsed since it started — matching Task 011,
Задача 2 ("автоматично освобождаване след изтичане на прозореца").
This is intentionally simpler than a sliding log; it can allow a short
burst around a window boundary, which is an acceptable trade-off for an
abuse-prevention mechanism, not a precise quota system.
"""
import time
from typing import Any, Dict, Tuple

from phoenix_core.utils.exceptions import RateLimitExceededError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_REQUESTS = 10
DEFAULT_WINDOW_SECONDS = 60


class RateLimiter:
    """Tracks and enforces a per-user request rate limit."""

    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        """Create a rate limiter.

        Args:
            max_requests: Max requests allowed per user within one window.
            window_seconds: Length of the window, in seconds.
        """
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # user_id -> (window_start_monotonic, count_in_window)
        self._windows: Dict[int, Tuple[float, int]] = {}

    def check(self, user_id: int) -> None:
        """Record one request attempt for `user_id`, enforcing the limit.

        Starts (or resets) the user's window as needed, then either counts
        this request or raises. Never logs anything about *what* the
        request was — only that a limit was hit.

        Raises:
            RateLimitExceededError: If the user has already made
                `max_requests` requests within the current window.
        """
        now = time.monotonic()
        window_start, count = self._windows.get(user_id, (now, 0))

        if now - window_start >= self._window_seconds:
            window_start, count = now, 0

        if count >= self._max_requests:
            logger.warning(
                "Rate limit hit",
                user_id=user_id,
                max_requests=self._max_requests,
                window_seconds=self._window_seconds,
            )
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {self._max_requests} requests per "
                f"{self._window_seconds}s"
            )

        self._windows[user_id] = (window_start, count + 1)

    @property
    def active_entries(self) -> int:
        """Number of users with a currently tracked (not-yet-expired) window."""
        now = time.monotonic()
        return sum(
            1 for window_start, _ in self._windows.values()
            if now - window_start < self._window_seconds
        )

    async def health_check(self) -> Dict[str, Any]:
        """Report RateLimiter status for the AI Guard health summary."""
        return {
            "status": "healthy",
            "active_entries": self.active_entries,
            "max_requests": self._max_requests,
            "window_seconds": self._window_seconds,
        }
