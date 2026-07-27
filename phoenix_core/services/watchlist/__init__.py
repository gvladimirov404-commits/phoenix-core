"""Watchlist persistence (Task 020, /watch): lets a Telegram user save a set
of coin symbols and retrieve them later — no notifications, storage only.
Mirrors the ConversationStore/ConversationManager split from Task 012
(phoenix_core/memory/storage/, phoenix_core/memory/manager.py) exactly —
same sync SQLite pattern, same Manager-wraps-Store shape — rather than
introducing a new persistence approach."""
from phoenix_core.services.watchlist.manager import WatchlistManager
from phoenix_core.services.watchlist.store import SQLiteWatchlistStore

__all__ = ["WatchlistManager", "SQLiteWatchlistStore"]
