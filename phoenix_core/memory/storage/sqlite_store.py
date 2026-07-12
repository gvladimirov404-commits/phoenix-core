"""
SQLiteConversationStore — stdlib sqlite3-backed ConversationStore (Task 012).

Plain `sqlite3` (synchronous, stdlib, no ORM), by explicit correction of
Task 012: ConversationManager's public API had to stay fully synchronous,
which ruled out real async I/O via aiosqlite (see Task 012 correction
note / final report for the reasoning). All SQL lives here and only here
— ConversationManager (phoenix_core/memory/manager.py) never builds a
query string.

A single sqlite3.Connection is opened once in initialize() and held for
the store's lifetime (see close()), rather than opened per call — this
is what makes `db_path=":memory:"` behave as a real, queryable database
for the lifetime of the store (each new connection to ":memory:" would
otherwise be a *different*, empty database). ConversationManager defaults
to `db_path=":memory:"` when no path is given, which keeps every existing
unit test's `ConversationManager(...)` construction isolated and
side-effect-free (Task 012, tests) while still exercising the exact same
SQL code path as a real file-backed database. Actual persistence across
restarts (Task 012's actual goal) comes from PhoenixApplication passing a
real file path from Settings.sqlite_database.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from phoenix_core.memory.models import Conversation, Message
from phoenix_core.memory.storage.base import ConversationStore
from phoenix_core.utils.exceptions import StorageError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
"""


class SQLiteConversationStore(ConversationStore):
    """Raw-SQL sqlite3 ConversationStore. One open connection, held for its lifetime."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Create a store for `db_path` (not yet connected — call initialize()).

        Args:
            db_path: Filesystem path to the SQLite database file, or the
                special value ":memory:" for an ephemeral database that
                lives only as long as this store's connection.
        """
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Open the connection (creating the file automatically if needed) and ensure schema exists.

        Raises:
            StorageError: If `db_path` exists but isn't a valid SQLite
                database (e.g. corrupted), or the connection/schema
                creation fails for any other sqlite3 reason. Callers
                (ConversationManager, PhoenixApplication) are expected to
                catch this and degrade rather than let a raw sqlite3
                traceback crash startup (Task 013, Задача 5).
        """
        if self._conn is not None:
            return  # already initialized — idempotent

        try:
            # check_same_thread=False: Phoenix Core is single-process asyncio
            # (one thread), so this only relaxes sqlite3's default same-thread
            # guard rather than introducing real multi-threaded access.
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(
                "Database initialization failed",
                database_path=self._db_path,
                error_type=type(e).__name__,
            )
            raise StorageError(
                f"Could not open or initialize the SQLite database at '{self._db_path}': {e}"
            ) from e

        self._conn = conn
        logger.info("Database opened", database_path=self._db_path)
        logger.info("Database initialized", database_path=self._db_path)

    def get_conversation(self, user_id: int) -> Optional[Conversation]:
        conn = self._require_conn()
        row = conn.execute(
            "SELECT id, user_id, created_at, updated_at FROM conversations WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        conversation_id, stored_user_id, created_at, updated_at = row
        message_rows = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        messages = [
            Message(role=role, content=content, timestamp=_parse_timestamp(timestamp))
            for role, content, timestamp in message_rows
        ]

        conversation = Conversation(
            conversation_id=conversation_id,
            user_id=stored_user_id,
            created_at=_parse_timestamp(created_at),
            updated_at=_parse_timestamp(updated_at),
            messages=messages,
        )
        logger.debug("Conversation loaded", user_id=user_id, message_count=len(messages))
        return conversation

    def create_conversation(self, user_id: int) -> Conversation:
        conn = self._require_conn()
        conversation_id = uuid4().hex
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        conn.execute(
            "INSERT INTO conversations (id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conversation_id, user_id, now_iso, now_iso),
        )
        conn.commit()
        return Conversation(conversation_id=conversation_id, user_id=user_id, created_at=now, updated_at=now)

    def insert_message(self, conversation_id: str, message: Message) -> None:
        conn = self._require_conn()
        timestamp_iso = message.timestamp.isoformat()
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conversation_id, message.role, message.content, timestamp_iso),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (timestamp_iso, conversation_id),
        )
        conn.commit()
        logger.info("Conversation saved", conversation_id=conversation_id)

    def trim_messages(self, conversation_id: str, max_messages: int) -> int:
        conn = self._require_conn()
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        overflow = count - max_messages
        if overflow <= 0:
            return 0

        conn.execute(
            "DELETE FROM messages WHERE id IN ("
            "  SELECT id FROM messages WHERE conversation_id = ? ORDER BY id ASC LIMIT ?"
            ")",
            (conversation_id, overflow),
        )
        conn.commit()
        logger.info("Memory trimmed", conversation_id=conversation_id, dropped=overflow)
        return overflow

    def delete_conversation(self, user_id: int) -> bool:
        conn = self._require_conn()
        row = conn.execute("SELECT id FROM conversations WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return False

        conversation_id = row[0]
        # Explicit delete rather than relying solely on ON DELETE CASCADE —
        # keeps behavior correct even if PRAGMA foreign_keys were ever off.
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        logger.info("Conversation deleted", user_id=user_id, conversation_id=conversation_id)
        return True

    def count_active_conversations(self) -> int:
        conn = self._require_conn()
        (count,) = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
        return count

    def count_total_messages(self) -> int:
        conn = self._require_conn()
        (count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        return count

    def health_check(self) -> Dict[str, Any]:
        try:
            self._require_conn().execute("SELECT 1")
            available = True
        except sqlite3.Error:
            available = False

        return {
            "status": "healthy" if available else "unhealthy",
            "backend": "sqlite",
            "database_available": available,
            "database_path": self._db_path,
            "active_conversations": self.count_active_conversations() if available else 0,
            "total_stored_messages": self.count_total_messages() if available else 0,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteConversationStore.initialize() must be called before use")
        return self._conn


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 string (as produced by datetime.isoformat()) back to a datetime."""
    return datetime.fromisoformat(value)
