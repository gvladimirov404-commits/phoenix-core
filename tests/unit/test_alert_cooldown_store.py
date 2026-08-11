"""Unit tests for SQLiteAlertCooldownStore (TASK-023 Phase G)."""
import os
import time

import pytest

from phoenix_core.services.research.alert_cooldown_store import (
    SQLiteAlertCooldownStore,
    build_fingerprint,
)


class TestInitialize:
    def test_creates_database_file_automatically(self, tmp_path) -> None:
        db_path = str(tmp_path / "auto.db")
        assert not os.path.exists(db_path)
        store = SQLiteAlertCooldownStore(db_path)
        store.initialize()
        assert os.path.exists(db_path)
        store.close()

    def test_idempotent_when_called_twice(self, tmp_path) -> None:
        db_path = str(tmp_path / "idempotent.db")
        store = SQLiteAlertCooldownStore(db_path)
        store.initialize()
        store.initialize()
        store.close()

    def test_memory_backend_works(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        assert store.should_alert("BTC", ["price"], 1800) is True
        store.close()


class TestFingerprint:
    def test_fingerprint_is_order_independent(self) -> None:
        assert build_fingerprint(["price", "news"]) == build_fingerprint(["news", "price"])

    def test_fingerprint_deduplicates(self) -> None:
        assert build_fingerprint(["price", "price"]) == build_fingerprint(["price"])


class TestFirstAlertAlwaysAllowed:
    def test_no_prior_record_allows_alert(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        assert store.should_alert("BTC", ["price"], 1800) is True
        store.close()


class TestCooldownSuppression:
    def test_same_fingerprint_within_window_suppressed(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        store.record_alert("BTC", ["price"])
        assert store.should_alert("BTC", ["price"], 1800) is False
        store.close()

    def test_same_fingerprint_after_window_allowed(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        store.record_alert("BTC", ["price"])
        # cooldown_seconds=0 means "already expired" for any elapsed time >= 0
        assert store.should_alert("BTC", ["price"], 0) is True
        store.close()


class TestFingerprintChangeBypassesCooldown:
    def test_different_fingerprint_allowed_even_within_window(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        store.record_alert("BTC", ["price"])
        assert store.should_alert("BTC", ["sentiment"], 1800) is True
        store.close()


class TestPersistenceAcrossRestart:
    def test_cooldown_survives_reopening_the_same_file(self, tmp_path) -> None:
        db_path = str(tmp_path / "cooldown_persist.db")

        store1 = SQLiteAlertCooldownStore(db_path)
        store1.initialize()
        store1.record_alert("BTC", ["price"])
        store1.close()

        store2 = SQLiteAlertCooldownStore(db_path)
        store2.initialize()
        assert store2.should_alert("BTC", ["price"], 1800) is False
        store2.close()


class TestSymbolIsolation:
    def test_different_symbols_are_independent(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        store.record_alert("BTC", ["price"])
        assert store.should_alert("ETH", ["price"], 1800) is True
        store.close()

    def test_symbol_lookup_is_case_insensitive(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        store.initialize()
        store.record_alert("btc", ["price"])
        assert store.should_alert("BTC", ["price"], 1800) is False
        store.close()


class TestHealthCheck:
    def test_reports_availability_and_path(self, tmp_path) -> None:
        db_path = str(tmp_path / "health.db")
        store = SQLiteAlertCooldownStore(db_path)
        store.initialize()
        health = store.health_check()
        assert health["status"] == "healthy"
        assert health["backend"] == "sqlite"
        assert health["database_path"] == db_path
        store.close()


class TestUninitializedUse:
    def test_using_store_before_initialize_raises(self) -> None:
        store = SQLiteAlertCooldownStore(":memory:")
        with pytest.raises(RuntimeError):
            store.should_alert("BTC", ["price"], 1800)
