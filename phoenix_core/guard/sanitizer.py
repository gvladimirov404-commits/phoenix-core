"""
OutputSanitizer — defensive cleanup of AI-generated text before it is sent
to Telegram (Task 011, Задача 5; truncation removed in Task 017 Part 1).

As of Task 017, this class has a single responsibility: neutralizing
unbalanced Markdown-ish tokens so a stray trailing "*"/"_"/"`" can't produce
a broken/confusing message if `parse_mode` is ever turned on. Length
limiting is no longer this class's job — the real defect (long AI answers
being cut with a "[съкратено...]" marker) is fixed by splitting long
responses into multiple Telegram messages at send time
(phoenix_core.telegram.bot._split_for_telegram), which preserves full
content instead of discarding it.
"""
from typing import Dict

MAX_TELEGRAM_MESSAGE_LENGTH = 4096
_MARKDOWN_TOKENS = ("```", "*", "_", "`")


class OutputSanitizer:
    """Applies bounded, defensive cleanup to text before it's sent to Telegram."""

    def __init__(self, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> None:
        """Create a sanitizer.

        Args:
            max_length: Retained for backward-compatible construction and
                reported by health_check(); no longer used to truncate
                content — see module docstring (Task 017).
        """
        if max_length < 1:
            raise ValueError("max_length must be a positive number of characters")
        self._max_length = max_length

    def sanitize(self, text: str) -> str:
        """Return `text` with balanced Markdown tokens. Never truncates."""
        return self._balance_markdown_tokens(text)

    @staticmethod
    def _balance_markdown_tokens(text: str) -> str:
        """Append the closing character for any Markdown-ish token left open.

        Checked longest-first so a stray ``` isn't miscounted as one and a
        half pairs of single backticks.
        """
        for token in _MARKDOWN_TOKENS:
            if text.count(token) % 2 != 0:
                text += token
        return text

    async def health_check(self) -> Dict[str, int]:
        """Report OutputSanitizer's configured limit for the AI Guard health summary."""
        return {"max_length": self._max_length}
