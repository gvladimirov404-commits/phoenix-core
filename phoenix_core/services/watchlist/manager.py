"""WatchlistManager — public-facing API for per-user coin watchlists (Task 020).

Mirrors phoenix_core.memory.manager.ConversationManager's role: a thin,
synchronous facade over the SQL store (commands.py never touches SQL or
the store directly), plus async start()/stop()/health_check() so
PhoenixApplication can manage it via the same duck-typed component
lifecycle as every other service in self._components.
"""
from typing import Any, Dict, List, Optional

from phoenix_core.services.watchlist.store import SQLiteWatchlistStore
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_SYMBOLS_PER_USER = 50


class WatchlistManager:
    """Synchronous CRUD API for per-user watchlists, backed by SQLiteWatchlistStore."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Create the manager and its store (raises StorageError if db_path is
        an existing, corrupted database — same contract as ConversationManager)."""
        self._store = SQLiteWatchlistStore(db_path=db_path)
        self._store.initialize()

    def get_watchlist(self, user_id: int) -> List[str]:
        """Return the user's current watchlist symbols, in the order they were added."""
        return self._store.get_watchlist(user_id)

    def add_symbols(self, user_id: int, symbols: List[str]) -> List[str]:
        """Add symbols to the user's watchlist (case-normalized, deduplicated,
        capped at _MAX_SYMBOLS_PER_USER total). Returns the full watchlist after adding."""
        normalized = []
        seen = set(self.get_watchlist(user_id))
        for symbol in symbols:
            clean = symbol.strip().upper()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            normalized.append(clean)

        current_count = len(self.get_watchlist(user_id))
        room = max(0, _MAX_SYMBOLS_PER_USER - current_count)
        return self._store.add_symbols(user_id, normalized[:room])

    def clear(self, user_id: int) -> int:
        """Remove every symbol from the user's watchlist. Returns the number removed."""
        return self._store.clear_watchlist(user_id)

    # ------------------------------------------------------------------
    # Component lifecycle (PhoenixApplication)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """No-op — the store is already initialized in __init__ (synchronous, like
        ConversationManager). Present only to satisfy the component lifecycle protocol."""
        return None

    async def stop(self) -> None:
        self._store.close()

    async def health_check(self) -> Dict[str, Any]:
        return self._store.health_check()

    def list_watchers(self, symbol: str) -> List[int]:
        """Return every user_id currently watching `symbol` (Task 023 Phase G)."""
        return self._store.list_watchers(symbol)

    def list_all_symbols(self) -> List[str]:
        """Return every distinct symbol currently watched by at least one
        user, across all watchlists (Task 023 Phase G)."""
        return self._store.list_all_symbols()
