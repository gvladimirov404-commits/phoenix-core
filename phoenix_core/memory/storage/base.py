"""
ConversationStore — backend-agnostic storage interface for Conversation
Memory (Task 012).

ConversationManager (phoenix_core/memory/manager.py) talks only to this
interface, never to SQL or any specific driver — "ConversationManager не
трябва да съдържа SQL" (Task 012, Задача 2). SQLiteConversationStore
(sqlite_store.py) is the only implementation today; a future Redis- or
aiosqlite-backed store just needs to implement this same interface, with
no change to ConversationManager or anything above it (commands.py,
ContextBuilder, AIRouter).

Deliberately synchronous: ConversationManager's public API is
synchronous by design decision (see Task 012 correction — "Не превръщай
синхронните методи в async"), so every method here is a plain blocking
call, not a coroutine. A future async backend would need an adapter at
this boundary, not a change to ConversationManager.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from phoenix_core.memory.models import Conversation, Message


class ConversationStore(ABC):
    """Backend-agnostic CRUD interface for Conversation persistence."""

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the backend for use (e.g. open a connection, create schema).

        Must be safe to call when storage already exists/is initialized
        (idempotent) — Task 012, Задача 4: "ако базата не съществува:
        създай я автоматично".
        """
        raise NotImplementedError

    @abstractmethod
    def get_conversation(self, user_id: int) -> Optional[Conversation]:
        """Return the user's stored conversation with its full message history, or None."""
        raise NotImplementedError

    @abstractmethod
    def create_conversation(self, user_id: int) -> Conversation:
        """Create and persist a new, empty conversation for `user_id`."""
        raise NotImplementedError

    @abstractmethod
    def insert_message(self, conversation_id: str, message: Message) -> None:
        """Persist one message under `conversation_id` and bump the conversation's updated_at."""
        raise NotImplementedError

    @abstractmethod
    def trim_messages(self, conversation_id: str, max_messages: int) -> int:
        """Delete the oldest messages under `conversation_id` beyond `max_messages`.

        Returns:
            Number of messages deleted (0 if already within the limit).
        """
        raise NotImplementedError

    @abstractmethod
    def delete_conversation(self, user_id: int) -> bool:
        """Delete the user's conversation and all its messages.

        Returns:
            True if a conversation existed and was deleted, False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def count_active_conversations(self) -> int:
        """Total number of stored conversations, across all users."""
        raise NotImplementedError

    @abstractmethod
    def count_total_messages(self) -> int:
        """Total number of stored messages, across every conversation."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Report backend health/config (Task 012, Задача 6)."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release any held resources (e.g. close a database connection)."""
        raise NotImplementedError
