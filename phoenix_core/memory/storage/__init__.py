"""
Storage backends for Conversation Memory (Task 012).

ConversationStore (base.py) is the backend-agnostic interface;
SQLiteConversationStore (sqlite_store.py) is the only implementation
today. See phoenix_core.memory.manager.ConversationManager for the
(unchanged, synchronous) public API that sits in front of whichever
store is configured.
"""
from phoenix_core.memory.storage.base import ConversationStore
from phoenix_core.memory.storage.sqlite_store import SQLiteConversationStore

__all__ = ["ConversationStore", "SQLiteConversationStore"]
