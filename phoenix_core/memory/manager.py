"""
ConversationManager — Conversation Memory Engine core (Task 010; SQLite
persistence added in Task 012).

Owns conversation lifecycle only: create, load, append messages, trim,
reset, and report stats. It never calls an AI provider and never imports
AIRouter — building an AI-request-shaped payload from a Conversation is
ContextBuilder's job, not this class's (see phoenix_core.memory.context_builder).

Public API is unchanged since Task 010 and remains fully synchronous —
this was an explicit Task 012 correction: ConversationManager's public
method signatures were kept stable in preference to using aiosqlite, so
every method here is still a plain `def`, not `async def` (health_check()
was already async since Task 010 and stays that way). See
phoenix_core.memory.storage for why this doesn't block real persistence:
storage access is delegated to a ConversationStore
(phoenix_core.memory.storage.base.ConversationStore), which does its own
synchronous, stdlib-only sqlite3 I/O — no SQL lives in this class, and no
caller of ConversationManager (commands.py, ContextBuilder) changed at
all going from Task 010's in-memory dict to Task 012's SQLite backend.

Storage backend is pluggable by construction, not by convention: pass a
different ConversationStore implementation (e.g. a future Redis-backed
one) via the `store` constructor argument and nothing else in this class
needs to change.

Never logs message content — only counts, ids, and timestamps
(Task 010, Задача 7 / Task 012, Задача 9).
"""
from typing import Any, Dict, Optional

from phoenix_core.memory.models import Conversation, Message, Role
from phoenix_core.memory.storage.base import ConversationStore
from phoenix_core.memory.storage.sqlite_store import SQLiteConversationStore
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_CONVERSATION_MESSAGES = 20
DEFAULT_DB_PATH = ":memory:"


class ConversationManager:
    """Creates, stores, and trims per-user Conversation history (SQLite-backed, V2)."""

    def __init__(
        self,
        max_messages: int = DEFAULT_MAX_CONVERSATION_MESSAGES,
        db_path: str = DEFAULT_DB_PATH,
        store: Optional[ConversationStore] = None,
    ) -> None:
        """Create a manager backed by `store` (a SQLiteConversationStore at `db_path` by default).

        Args:
            max_messages: Maximum number of messages kept per conversation.
                Once exceeded, the oldest messages are dropped first
                (Task 010, Задача 4 — Settings.ai_max_conversation_messages
                is the real source in the running app).
            db_path: Path to the SQLite database file used when `store`
                isn't given. Defaults to ":memory:" — an ephemeral,
                isolated database scoped to this manager's lifetime, which
                is what every existing unit test gets automatically. The
                running app passes a real file path (Settings.sqlite_database)
                so conversations persist across restarts (Task 012's goal).
            store: An already-constructed ConversationStore to use instead
                of creating a default SQLiteConversationStore — the seam a
                future backend (Redis, aiosqlite, ...) plugs into.
        """
        if max_messages < 1:
            raise ValueError("max_messages must be at least 1")
        self._max_messages = max_messages
        self._store = store or SQLiteConversationStore(db_path)
        self._store.initialize()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def get_or_create(self, user_id: int) -> Conversation:
        """Return the user's current conversation, creating one if none exists yet."""
        conversation = self._store.get_conversation(user_id)
        if conversation is not None:
            return conversation

        conversation = self._store.create_conversation(user_id)
        logger.info("Conversation created", user_id=user_id, conversation_id=conversation.conversation_id)
        return conversation

    def add_message(self, user_id: int, role: Role, content: str) -> Conversation:
        """Append one message to the user's conversation, trimming if over the limit.

        Creates the conversation first if the user has none yet. Returns the
        updated Conversation, re-read from storage so it reflects the new
        message and any trimming that just happened.
        """
        conversation = self.get_or_create(user_id)
        self._store.insert_message(conversation.conversation_id, Message(role=role, content=content))
        self._store.trim_messages(conversation.conversation_id, self._max_messages)
        return self._store.get_conversation(user_id)

    def reset(self, user_id: int) -> bool:
        """Delete the user's current conversation, if any.

        Returns:
            True if a conversation existed and was removed, False if the
            user had none (still a successful, idempotent no-op).
        """
        existed = self._store.delete_conversation(user_id)
        logger.info("Conversation reset", user_id=user_id, existed=existed)
        return existed

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Return summary stats for /memory, or None if the user has no conversation.

        Never includes message content — only counts, ids, and timestamps.
        """
        conversation = self._store.get_conversation(user_id)
        if conversation is None:
            return None

        context_chars = sum(len(m.content) for m in conversation.messages)
        return {
            "conversation_id": conversation.conversation_id,
            "message_count": len(conversation.messages),
            "context_chars": context_chars,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    @property
    def active_conversations(self) -> int:
        """Number of users with a currently stored conversation."""
        return self._store.count_active_conversations()

    @property
    def total_stored_messages(self) -> int:
        """Total message count across every stored conversation."""
        return self._store.count_total_messages()

    async def health_check(self) -> Dict[str, Any]:
        """Report Conversation Memory health for /health and /status.

        Delegates to the store for backend-specific fields (Task 012,
        Задача 6: database availability, path, active conversations, total
        messages) — this method stays async only because it already was
        since Task 010; the underlying call is a synchronous, fast local
        sqlite3 query.
        """
        return self._store.health_check()

    async def stop(self) -> None:
        """Release the storage backend's resources (e.g. close the SQLite connection).

        Optional lifecycle hook — PhoenixApplication.stop() calls this if
        present, same pattern as every other component.
        """
        self._store.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    # No SQL, no storage details here by design (Task 012, Задача 2) — all
    # of that lives in phoenix_core.memory.storage.
