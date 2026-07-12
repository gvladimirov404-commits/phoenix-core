"""
Conversation Memory Engine (Task 010; SQLite persistence added in Task 012).

A small, self-contained module that gives Phoenix Core short-term
conversation memory: per-user message history that AIRouter.chat() can
be given as context, without AIRouter or any AI Provider needing to know
how (or whether) that history is stored.

Public surface:
    Message, Conversation       — plain data models (phoenix_core.memory.models)
    ConversationManager         — owns conversation lifecycle/storage (phoenix_core.memory.manager)
    ContextBuilder               — Conversation -> AIRouter message list (phoenix_core.memory.context_builder)
    ConversationStore            — backend-agnostic storage interface (phoenix_core.memory.storage)
    SQLiteConversationStore      — sqlite3-backed ConversationStore (phoenix_core.memory.storage)

Storage is pluggable behind ConversationStore (phoenix_core/memory/storage/):
SQLiteConversationStore (stdlib sqlite3, no ORM) is the only
implementation today, and is what ConversationManager uses by default —
conversations persist across restarts via Settings.sqlite_database. A
future Redis/aiosqlite-backed store just needs to implement the same
interface; nothing above ConversationManager changes.
"""
from phoenix_core.memory.context_builder import ContextBuilder
from phoenix_core.memory.manager import ConversationManager
from phoenix_core.memory.models import Conversation, Message
from phoenix_core.memory.storage import ConversationStore, SQLiteConversationStore

__all__ = [
    "Message",
    "Conversation",
    "ConversationManager",
    "ContextBuilder",
    "ConversationStore",
    "SQLiteConversationStore",
]
