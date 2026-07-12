"""
CostGuard — size-based protection against oversized requests (Task 011).

Deliberately works only with input *size* (characters), never with an
estimated monetary cost — see Task 011, Задача 3: "Не използвай
приблизителни оценки на цена в пари. Работи само с размер на входа."

Two independent checks, both belt-and-suspenders on top of existing
Task 010 behavior rather than a replacement for it:

- check_prompt(): mirrors the ad hoc `ai_max_prompt_length` check that
  already lived in phoenix_core.telegram.commands.cmd_ask — centralizing
  it here doesn't remove that check (cmd_ask still runs it first, for a
  fast/free rejection with no Guard dependency), it gives the Guard Layer
  its own authoritative copy for when it *is* wired up.
- check_context(): a hard ceiling on the final assembled message list
  about to be sent to a provider. This is intentionally a *higher* limit
  than ContextBuilder's own `max_context_chars` (which already silently
  trims oldest-first on every /ask) — it exists to catch the case where
  context reaches AIRouter.chat() through a path that bypassed
  ContextBuilder's trimming (e.g. Conversation Memory being unavailable
  and a caller assembling messages some other way), not to duplicate
  ContextBuilder's normal trimming behavior.
"""
from typing import Dict, List

from phoenix_core.utils.exceptions import ContextTooLargeError, PromptTooLargeError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_PROMPT_CHARS = 4000
DEFAULT_MAX_CONTEXT_CHARS = 12000


class CostGuard:
    """Rejects prompts or assembled contexts that exceed configured size ceilings."""

    def __init__(
        self,
        max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        """Create a cost guard.

        Args:
            max_prompt_chars: Max length of a single prompt, in characters.
            max_context_chars: Max combined length of an assembled message
                list about to be sent to a provider, in characters.
        """
        if max_prompt_chars < 1:
            raise ValueError("max_prompt_chars must be at least 1")
        if max_context_chars < 1:
            raise ValueError("max_context_chars must be at least 1")
        self._max_prompt_chars = max_prompt_chars
        self._max_context_chars = max_context_chars

    def check_prompt(self, prompt: str) -> None:
        """Raise PromptTooLargeError if `prompt` exceeds the configured limit."""
        length = len(prompt)
        if length > self._max_prompt_chars:
            logger.warning(
                "Oversized prompt rejected",
                prompt_length=length,
                max_prompt_chars=self._max_prompt_chars,
            )
            raise PromptTooLargeError(
                f"Prompt too large: {length} chars (max {self._max_prompt_chars})"
            )

    def check_context(self, messages: List[Dict[str, str]]) -> None:
        """Raise ContextTooLargeError if the combined `messages` content exceeds the limit."""
        length = sum(len(m.get("content", "")) for m in messages)
        if length > self._max_context_chars:
            logger.warning(
                "Oversized context rejected",
                context_length=length,
                max_context_chars=self._max_context_chars,
            )
            raise ContextTooLargeError(
                f"Context too large: {length} chars (max {self._max_context_chars})"
            )

    async def health_check(self) -> Dict[str, int]:
        """Report CostGuard's configured limits for the AI Guard health summary."""
        return {
            "max_prompt_chars": self._max_prompt_chars,
            "max_context_chars": self._max_context_chars,
        }
