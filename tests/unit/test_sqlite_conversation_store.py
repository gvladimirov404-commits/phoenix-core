"""Unit tests for phoenix_core.memory.storage.sqlite_store.SQLiteConversationStore."""
import os

import pytest

from phoenix_core.memory.models import Message
from phoenix_core.memory.storage.sqlite_store import SQLiteConversationStore


class TestInitialize:
    def test_creates_database_file_automatically(self, tmp_path) -> None:
        db_path = str(tmp_path / "auto_created.db")
        assert not os.path.exists(db_path)

        store = SQLiteConversationStore(db_path)
        store.initialize()

        assert os.path.exists(db_path)
        store.close()

    def test_idempotent_when_called_twice(self, tmp_path) -> None:
        db_path = str(tmp_path / "idempotent.db")
        store = SQLiteConversationStore(db_path)
        store.initialize()
        store.initialize()  # should not raise or reset anything
        store.close()

    def test_memory_backend_works_without_a_file(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        assert store.get_conversation(1) is None
        store.close()


class TestCrud:
    def test_create_and_get_conversation(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()

        created = store.create_conversation(user_id=1)
        fetched = store.get_conversation(user_id=1)

        assert fetched is not None
        assert fetched.conversation_id == created.conversation_id
        assert fetched.user_id == 1
        assert fetched.messages == []
        store.close()

    def test_get_conversation_returns_none_when_absent(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        assert store.get_conversation(999) is None
        store.close()

    def test_insert_message_persists_and_orders_correctly(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv = store.create_conversation(user_id=1)

        store.insert_message(conv.conversation_id, Message(role="user", content="first"))
        store.insert_message(conv.conversation_id, Message(role="assistant", content="second"))

        fetched = store.get_conversation(1)
        assert [m.content for m in fetched.messages] == ["first", "second"]
        assert [m.role for m in fetched.messages] == ["user", "assistant"]
        store.close()

    def test_insert_message_bumps_updated_at(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv = store.create_conversation(user_id=1)
        original_updated_at = conv.updated_at

        store.insert_message(conv.conversation_id, Message(role="user", content="hi"))

        fetched = store.get_conversation(1)
        assert fetched.updated_at >= original_updated_at
        store.close()

    def test_delete_conversation_removes_conversation_and_messages(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv = store.create_conversation(user_id=1)
        store.insert_message(conv.conversation_id, Message(role="user", content="hi"))

        deleted = store.delete_conversation(1)

        assert deleted is True
        assert store.get_conversation(1) is None
        assert store.count_total_messages() == 0
        store.close()

    def test_delete_conversation_returns_false_when_absent(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        assert store.delete_conversation(999) is False
        store.close()


class TestTrim:
    def test_trim_deletes_oldest_messages_beyond_limit(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv = store.create_conversation(user_id=1)
        for i in range(5):
            store.insert_message(conv.conversation_id, Message(role="user", content=f"msg-{i}"))

        deleted_count = store.trim_messages(conv.conversation_id, max_messages=3)

        assert deleted_count == 2
        fetched = store.get_conversation(1)
        assert [m.content for m in fetched.messages] == ["msg-2", "msg-3", "msg-4"]
        store.close()

    def test_trim_no_op_when_within_limit(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv = store.create_conversation(user_id=1)
        store.insert_message(conv.conversation_id, Message(role="user", content="hi"))

        deleted_count = store.trim_messages(conv.conversation_id, max_messages=10)

        assert deleted_count == 0
        store.close()


class TestCounts:
    def test_counts_across_multiple_users(self) -> None:
        store = SQLiteConversationStore(":memory:")
        store.initialize()
        conv1 = store.create_conversation(user_id=1)
        conv2 = store.create_conversation(user_id=2)
        store.insert_message(conv1.conversation_id, Message(role="user", content="a"))
        store.insert_message(conv2.conversation_id, Message(role="user", content="b"))
        store.insert_message(conv2.conversation_id, Message(role="assistant", content="c"))

        assert store.count_active_conversations() == 2
        assert store.count_total_messages() == 3
        store.close()


class TestPersistenceAcrossRestart:
    def test_data_survives_reopening_the_same_file(self, tmp_path) -> None:
        db_path = str(tmp_path / "persist.db")

        store1 = SQLiteConversationStore(db_path)
        store1.initialize()
        conv = store1.create_conversation(user_id=7)
        store1.insert_message(conv.conversation_id, Message(role="user", content="before restart"))
        store1.close()

        # Simulate an application restart: brand new store, same file.
        store2 = SQLiteConversationStore(db_path)
        store2.initialize()
        fetched = store2.get_conversation(7)

        assert fetched is not None
        assert fetched.conversation_id == conv.conversation_id
        assert len(fetched.messages) == 1
        assert fetched.messages[0].content == "before restart"
        store2.close()


class TestHealthCheck:
    def test_reports_availability_path_and_counts(self, tmp_path) -> None:
        db_path = str(tmp_path / "health.db")
        store = SQLiteConversationStore(db_path)
        store.initialize()
        conv = store.create_conversation(user_id=1)
        store.insert_message(conv.conversation_id, Message(role="user", content="hi"))

        health = store.health_check()

        assert health["status"] == "healthy"
        assert health["backend"] == "sqlite"
        assert health["database_available"] is True
        assert health["database_path"] == db_path
        assert health["active_conversations"] == 1
        assert health["total_stored_messages"] == 1
        store.close()


class TestCorruptedDatabase:
    """Task 013 error-scenario audit: a corrupted DB file must fail clearly, not crash raw."""

    def test_corrupted_database_file_raises_storage_error(self, tmp_path) -> None:
        from phoenix_core.utils.exceptions import StorageError

        db_path = str(tmp_path / "corrupt.db")
        with open(db_path, "wb") as f:
            f.write(b"this is not a valid sqlite database file")

        store = SQLiteConversationStore(db_path)
        with pytest.raises(StorageError):
            store.initialize()

    def test_corrupted_database_does_not_leave_a_half_open_connection(self, tmp_path) -> None:
        from phoenix_core.utils.exceptions import StorageError

        db_path = str(tmp_path / "corrupt2.db")
        with open(db_path, "wb") as f:
            f.write(b"garbage")

        store = SQLiteConversationStore(db_path)
        with pytest.raises(StorageError):
            store.initialize()

        # Using the store afterward should raise the "not initialized" error,
        # not silently operate on a broken connection.
        with pytest.raises(RuntimeError):
            store.get_conversation(1)


class TestUninitializedUse:
    def test_using_store_before_initialize_raises(self) -> None:
        store = SQLiteConversationStore(":memory:")
        with pytest.raises(RuntimeError):
            store.get_conversation(1)
