"""
ContextBuilder — Conversation -> AIRouter.chat() message list (Task 010).

The only piece of the Memory Engine that knows AIRouter's expected input
shape (`List[Dict[str, str]]` with "role"/"content" keys — see
AIRouter._validate_messages). ConversationManager itself has no idea this
shape exists; it just stores Message/Conversation. AIRouter, in turn, has
no idea this builder or ConversationManager exist — it only ever sees a
plain message list, exactly as before Task 010 (Задача 3: "AIRouter не
трябва да знае как се пази паметта").

Applies a second, independent limit on top of ConversationManager's
message-count trimming: a maximum total character budget for the built
context (Task 010, Задача 4 — "максимален размер на контекста"). This
never mutates the stored Conversation — it only decides what subset of
the already-trimmed history is sent for *this* request, dropping the
oldest messages first and always keeping at least the most recent one.
"""
from typing import Dict, List

from phoenix_core.memory.models import Conversation

DEFAULT_MAX_CONTEXT_CHARS = 8000


class ContextBuilder:
    """Builds an AIRouter-ready message list from a Conversation."""

    def __init__(self, max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> None:
        """Create a builder.

        Args:
            max_context_chars: Maximum combined character length of the
                messages included in a built context. Older messages are
                dropped first once this is exceeded.
        """
        if max_context_chars < 1:
            raise ValueError("max_context_chars must be at least 1")
        self._max_context_chars = max_context_chars

    def build(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Return conversation.messages as an AIRouter-ready message list.

        Oldest-first order is preserved. If the combined character length
        exceeds max_context_chars, the oldest messages are dropped first —
        but the single most recent message is always kept, even if it
        alone exceeds the budget (AIRouter, not this builder, is
        responsible for rejecting an individually-too-long prompt).
        """
        if not conversation.messages:
            return []

        kept_reversed: List[Dict[str, str]] = []
        running_chars = 0
        for message in reversed(conversation.messages):
            message_chars = len(message.content)
            if kept_reversed and running_chars + message_chars > self._max_context_chars:
                break
            running_chars += message_chars
            kept_reversed.append({"role": message.role, "content": message.content})

        return list(reversed(kept_reversed))
