"""SQLiteWatchlistStore — stdlib sqlite3-backed storage for per-user coin
watchlists (Task 020). Mirrors phoenix_core.memory.storage.sqlite_store.
SQLiteConversationStore exactly: one connection opened in initialize() and
held for the store's lifetime (so db_path=":memory:" behaves as a real
database for tests), plain sqlite3 (no ORM), all SQL lives here only.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from phoenix_core.utils.exceptions import StorageError
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(user_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id ON watchlist_items(user_id);
"""


class SQLiteWatchlistStore:
    """Raw-SQL sqlite3 watchlist store. One open connection, held for its lifetime."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Create a store for `db_path` (not yet connected — call initialize())."""
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Open the connection (creating the file automatically if needed) and ensure schema exists.

        Raises:
            StorageError: If `db_path` exists but isn't a valid SQLite
                database, or schema creation otherwise fails — callers are
                expected to catch this and degrade (Task 012's precedent).
        """
        if self._conn is not None:
            return  # already initialized — idempotent

        try:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(
                "Watchlist database initialization failed",
                database_path=self._db_path,
                error_type=type(e).__name__,
            )
            raise StorageError(
                f"Could not open or initialize the watchlist SQLite database at '{self._db_path}': {e}"
            ) from e

        self._conn = conn
        logger.info("Watchlist database opened", database_path=self._db_path)

    def get_watchlist(self, user_id: int) -> List[str]:
        conn = self._require_conn()
        rows = conn.execute(
            "SELECT symbol FROM watchlist_items WHERE user_id = ? ORDER BY added_at ASC",
            (user_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def add_symbols(self, user_id: int, symbols: List[str]) -> List[str]:
        """Add symbols to the user's watchlist (idempotent — duplicates are ignored).

        Returns:
            The full watchlist after the addition.
        """
        conn = self._require_conn()
        now_iso = datetime.now(timezone.utc).isoformat()
        for symbol in symbols:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist_items (user_id, symbol, added_at) VALUES (?, ?, ?)",
                (user_id, symbol, now_iso),
            )
        conn.commit()
        logger.info("Watchlist updated", user_id=user_id, added_count=len(symbols))
        return self.get_watchlist(user_id)

    def clear_watchlist(self, user_id: int) -> int:
        conn = self._require_conn()
        cursor = conn.execute("DELETE FROM watchlist_items WHERE user_id = ?", (user_id,))
        conn.commit()
        deleted = cursor.rowcount
        logger.info("Watchlist cleared", user_id=user_id, deleted_count=deleted)
        return deleted

    def count_active_watchlists(self) -> int:
        conn = self._require_conn()
        (count,) = conn.execute("SELECT COUNT(DISTINCT user_id) FROM watchlist_items").fetchone()
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
            "active_watchlists": self.count_active_watchlists() if available else 0,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        """Safety-net finalizer — see SQLiteConversationStore.__del__ for the rationale."""
        try:
            self.close()
        except Exception:
            pass

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteWatchlistStore.initialize() must be called before use")
        return self._conn
