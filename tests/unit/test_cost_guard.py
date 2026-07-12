"""Unit tests for phoenix_core.guard.cost_guard.CostGuard."""
import pytest

from phoenix_core.guard.cost_guard import CostGuard
from phoenix_core.utils.exceptions import ContextTooLargeError, PromptTooLargeError


class TestCheckPrompt:
    def test_prompt_within_limit_passes(self) -> None:
        guard = CostGuard(max_prompt_chars=10)
        guard.check_prompt("short")  # should not raise

    def test_prompt_over_limit_raises(self) -> None:
        guard = CostGuard(max_prompt_chars=5)
        with pytest.raises(PromptTooLargeError):
            guard.check_prompt("this is way too long")

    def test_prompt_exactly_at_limit_passes(self) -> None:
        guard = CostGuard(max_prompt_chars=5)
        guard.check_prompt("12345")  # exactly 5 chars, should not raise


class TestCheckContext:
    def test_context_within_limit_passes(self) -> None:
        guard = CostGuard(max_context_chars=20)
        guard.check_context([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])

    def test_context_over_limit_raises(self) -> None:
        guard = CostGuard(max_context_chars=5)
        with pytest.raises(ContextTooLargeError):
            guard.check_context([
                {"role": "user", "content": "0123456789"},
                {"role": "assistant", "content": "0123456789"},
            ])

    def test_empty_context_passes(self) -> None:
        guard = CostGuard(max_context_chars=5)
        guard.check_context([])


class TestConstruction:
    def test_invalid_max_prompt_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            CostGuard(max_prompt_chars=0)

    def test_invalid_max_context_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            CostGuard(max_context_chars=0)


class TestHealthCheck:
    async def test_reports_configured_limits(self) -> None:
        guard = CostGuard(max_prompt_chars=100, max_context_chars=200)
        health = await guard.health_check()
        assert health == {"max_prompt_chars": 100, "max_context_chars": 200}
