"""Unit tests for phoenix_core.memory.manager.ConversationManager."""
import pytest

from phoenix_core.memory.manager import ConversationManager


class TestCreateAndLoad:
    def test_get_or_create_creates_new_conversation(self) -> None:
        manager = ConversationManager()
        conversation = manager.get_or_create(user_id=1)

        assert conversation.user_id == 1
        assert conversation.conversation_id
        assert conversation.messages == []

    def test_get_or_create_returns_same_conversation_on_second_call(self) -> None:
        manager = ConversationManager()
        first = manager.get_or_create(user_id=1)
        second = manager.get_or_create(user_id=1)

        # Value equality, not object identity — the SQLite backend (Task 012)
        # reconstructs a fresh Conversation from storage on every call.
        assert first == second
        assert first.conversation_id == second.conversation_id

    def test_different_users_get_different_conversations(self) -> None:
        manager = ConversationManager()
        conv_a = manager.get_or_create(user_id=1)
        conv_b = manager.get_or_create(user_id=2)

        assert conv_a.conversation_id != conv_b.conversation_id


class TestAddMessage:
    def test_add_message_appends_to_history(self) -> None:
        manager = ConversationManager()
        manager.add_message(1, "user", "Здравей")
        conversation = manager.add_message(1, "assistant", "Здрасти!")

        assert [m.role for m in conversation.messages] == ["user", "assistant"]
        assert [m.content for m in conversation.messages] == ["Здравей", "Здрасти!"]

    def test_add_message_updates_updated_at(self) -> None:
        manager = ConversationManager()
        conversation = manager.get_or_create(1)
        original_updated_at = conversation.updated_at

        updated = manager.add_message(1, "user", "hi")

        assert updated.updated_at >= original_updated_at


class TestHistoryLimit:
    def test_oldest_messages_dropped_once_over_limit(self) -> None:
        manager = ConversationManager(max_messages=3)
        for i in range(5):
            manager.add_message(1, "user", f"msg-{i}")

        conversation = manager.get_or_create(1)

        assert len(conversation.messages) == 3
        assert [m.content for m in conversation.messages] == ["msg-2", "msg-3", "msg-4"]

    def test_invalid_max_messages_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConversationManager(max_messages=0)


class TestReset:
    def test_reset_removes_conversation(self) -> None:
        manager = ConversationManager()
        manager.add_message(1, "user", "hi")

        existed = manager.reset(1)

        assert existed is True
        assert manager.get_stats(1) is None

    def test_reset_on_nonexistent_conversation_returns_false(self) -> None:
        manager = ConversationManager()
        assert manager.reset(1) is False

    def test_next_get_or_create_after_reset_makes_a_new_conversation(self) -> None:
        manager = ConversationManager()
        first = manager.get_or_create(1)
        manager.reset(1)
        second = manager.get_or_create(1)

        assert first.conversation_id != second.conversation_id


class TestStats:
    def test_get_stats_returns_none_when_no_conversation(self) -> None:
        manager = ConversationManager()
        assert manager.get_stats(1) is None

    def test_get_stats_reports_counts_without_content(self) -> None:
        manager = ConversationManager()
        manager.add_message(1, "user", "12345")
        manager.add_message(1, "assistant", "1234567890")

        stats = manager.get_stats(1)

        assert stats["message_count"] == 2
        assert stats["context_chars"] == 15
        assert "content" not in stats
        assert "messages" not in stats


class TestConcurrentUsers:
    def test_independent_conversations_for_different_users(self) -> None:
        manager = ConversationManager(max_messages=5)
        manager.add_message(1, "user", "alice-1")
        manager.add_message(2, "user", "bob-1")
        manager.add_message(1, "user", "alice-2")

        assert manager.get_stats(1)["message_count"] == 2
        assert manager.get_stats(2)["message_count"] == 1
        assert manager.active_conversations == 2
        assert manager.total_stored_messages == 3


class TestCorruptedDatabase:
    """Task 013: ConversationManager must propagate a clear StorageError, not a raw sqlite3 crash,
    so PhoenixApplication can catch it and degrade to in-memory instead of failing to start."""

    def test_corrupted_database_raises_storage_error_not_raw_sqlite_error(self, tmp_path) -> None:
        from phoenix_core.utils.exceptions import StorageError

        db_path = str(tmp_path / "corrupt.db")
        with open(db_path, "wb") as f:
            f.write(b"not a real sqlite database")

        with pytest.raises(StorageError):
            ConversationManager(db_path=db_path)


class TestPluggableStore:
    """Task 012: ConversationManager must work with any ConversationStore implementation,
    proving the backend can be swapped without changing ConversationManager itself."""

    def test_accepts_a_custom_store_injected_via_constructor(self) -> None:
        from datetime import datetime, timezone
        from typing import Any, Dict, Optional
        from uuid import uuid4

        from phoenix_core.memory.models import Conversation
        from phoenix_core.memory.storage.base import ConversationStore

        class FakeInMemoryStore(ConversationStore):
            """Minimal fake store — proves ConversationManager only depends on the interface."""

            def __init__(self) -> None:
                self._data: Dict[int, Conversation] = {}
                self.initialize_called = False

            def initialize(self) -> None:
                self.initialize_called = True

            def get_conversation(self, user_id: int) -> Optional[Conversation]:
                return self._data.get(user_id)

            def create_conversation(self, user_id: int) -> Conversation:
                conv = Conversation(conversation_id=uuid4().hex, user_id=user_id)
                self._data[user_id] = conv
                return conv

            def insert_message(self, conversation_id: str, message) -> None:
                for conv in self._data.values():
                    if conv.conversation_id == conversation_id:
                        conv.messages.append(message)
                        conv.updated_at = datetime.now(timezone.utc)

            def trim_messages(self, conversation_id: str, max_messages: int) -> int:
                return 0

            def delete_conversation(self, user_id: int) -> bool:
                return self._data.pop(user_id, None) is not None

            def count_active_conversations(self) -> int:
                return len(self._data)

            def count_total_messages(self) -> int:
                return sum(len(c.messages) for c in self._data.values())

            def health_check(self) -> Dict[str, Any]:
                return {"status": "healthy", "backend": "fake"}

            def close(self) -> None:
                pass

        fake_store = FakeInMemoryStore()
        manager = ConversationManager(store=fake_store)

        assert fake_store.initialize_called is True

        manager.add_message(1, "user", "hi")
        stats = manager.get_stats(1)

        assert stats["message_count"] == 1
        assert manager.active_conversations == 1


class TestHealthCheck:
    async def test_health_check_reports_active_and_total(self) -> None:
        manager = ConversationManager()
        manager.add_message(1, "user", "hi")
        manager.add_message(2, "user", "hi")
        manager.add_message(2, "assistant", "hello")

        health = await manager.health_check()

        assert health["status"] == "healthy"
        assert health["active_conversations"] == 2
        assert health["total_stored_messages"] == 3

    async def test_health_check_reports_sqlite_backend_details(self, tmp_path) -> None:
        db_path = str(tmp_path / "health.db")
        manager = ConversationManager(db_path=db_path)

        health = await manager.health_check()

        assert health["backend"] == "sqlite"
        assert health["database_available"] is True
        assert health["database_path"] == db_path


class TestPersistenceAcrossRestart:
    """Task 012: conversations must survive an application restart."""

    async def test_conversation_survives_a_new_manager_instance_on_the_same_db(self, tmp_path) -> None:
        db_path = str(tmp_path / "restart.db")

        manager_before_restart = ConversationManager(max_messages=20, db_path=db_path)
        manager_before_restart.add_message(7, "user", "before restart")
        manager_before_restart.add_message(7, "assistant", "reply")
        conversation_id_before = manager_before_restart.get_stats(7)["conversation_id"]
        await manager_before_restart.stop()  # simulate a clean app shutdown

        # A brand new ConversationManager, same db_path — simulates process restart.
        manager_after_restart = ConversationManager(max_messages=20, db_path=db_path)
        stats_after_restart = manager_after_restart.get_stats(7)

        assert stats_after_restart is not None
        assert stats_after_restart["conversation_id"] == conversation_id_before
        assert stats_after_restart["message_count"] == 2

    async def test_reset_persists_across_restart_too(self, tmp_path) -> None:
        db_path = str(tmp_path / "restart_reset.db")

        manager_before = ConversationManager(db_path=db_path)
        manager_before.add_message(1, "user", "hi")
        manager_before.reset(1)
        await manager_before.stop()

        manager_after = ConversationManager(db_path=db_path)
        assert manager_after.get_stats(1) is None

    def test_default_db_path_is_memory_and_isolated_per_instance(self) -> None:
        """Without an explicit db_path, each manager gets its own private database —
        this is what keeps every other test in this file isolated and side-effect-free."""
        manager_a = ConversationManager()
        manager_b = ConversationManager()

        manager_a.add_message(1, "user", "only in manager_a")

        assert manager_a.get_stats(1) is not None
        assert manager_b.get_stats(1) is None
