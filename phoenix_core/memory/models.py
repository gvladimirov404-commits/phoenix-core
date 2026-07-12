"""
Plain data models for the Conversation Memory Engine (Task 010).

These are intentionally dumb containers: no storage, no trimming policy,
no AI-provider-specific formatting. That logic lives in ConversationManager
and ContextBuilder respectively, so these models stay reusable regardless
of what backs conversation storage later (in-memory dict today; Redis or
SQLite later — see ConversationManager).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class Message:
    """A single turn in a conversation.

    Attributes:
        role: Who produced this message — "system", "user", or "assistant".
        content: The message text. Never logged (Task 010, Задача 7).
        timestamp: UTC time the message was recorded.
    """

    role: Role
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class Conversation:
    """A user's current conversation: metadata plus an ordered message history.

    Attributes:
        conversation_id: Opaque unique id for this conversation.
        user_id: Id of the user this conversation belongs to.
        created_at: UTC time the conversation was created.
        updated_at: UTC time of the most recent message added.
        messages: Ordered list of Message, oldest first. Trimming (dropping
            the oldest messages once a limit is exceeded) is the
            responsibility of ConversationManager, not this model.
    """

    conversation_id: str
    user_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: List[Message] = field(default_factory=list)
