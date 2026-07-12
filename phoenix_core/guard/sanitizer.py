"""
OutputSanitizer — defensive cleanup of AI-generated text before it is sent
to Telegram (Task 011, Задача 5).

Two independent, narrowly-scoped protections, deliberately not a full
Markdown parser/formatter — Task 011 explicitly says "Не променяй
съдържанието повече от необходимото":

1. Length: Telegram rejects `sendMessage` calls over 4096 characters.
   Responses over that are truncated with a clear Bulgarian marker rather
   than letting the send fail outright.
2. Unbalanced Markdown-ish tokens: phoenix_core.telegram.commands does not
   currently set a Telegram `parse_mode`, so `*`/`_`/`` ` `` are inert
   today — but an odd count of any of them is a plausible source of a
   broken/confusing message the moment `parse_mode` is ever turned on, so
   an unmatched trailing token is neutralized (escaped) defensively.
"""
from typing import Dict

MAX_TELEGRAM_MESSAGE_LENGTH = 4096
_TRUNCATION_SUFFIX = "\n\n… [съкратено, отговорът беше твърде дълъг]"
_MARKDOWN_TOKENS = ("```", "*", "_", "`")


class OutputSanitizer:
    """Applies bounded, defensive cleanup to text before it's sent to Telegram."""

    def __init__(self, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> None:
        """Create a sanitizer.

        Args:
            max_length: Telegram's message length ceiling, in characters.
        """
        if max_length < len(_TRUNCATION_SUFFIX) + 1:
            raise ValueError("max_length must comfortably fit the truncation suffix")
        self._max_length = max_length

    def sanitize(self, text: str) -> str:
        """Return `text`, truncated to the length limit and with balanced Markdown tokens.

        Order matters: tokens are balanced first (on the full text), then
        the result is truncated — truncating first could itself create a
        new unbalanced token right at the cut point.
        """
        cleaned = self._balance_markdown_tokens(text)
        return self._truncate(cleaned)

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

    def _truncate(self, text: str) -> str:
        if len(text) <= self._max_length:
            return text
        cutoff = self._max_length - len(_TRUNCATION_SUFFIX)
        return text[:cutoff].rstrip() + _TRUNCATION_SUFFIX

    async def health_check(self) -> Dict[str, int]:
        """Report OutputSanitizer's configured limit for the AI Guard health summary."""
        return {"max_length": self._max_length}
