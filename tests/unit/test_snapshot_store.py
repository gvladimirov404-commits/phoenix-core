"""Unit tests for phoenix_core.services.research.snapshot_store.SQLiteSnapshotStore."""
import os
from types import SimpleNamespace

import pytest

from phoenix_core.services.research.snapshot_store import SQLiteSnapshotStore


def _fake_snapshot(symbol="BTC", price=None, change_pct=None, fg_value=None,
                    fg_class=None, news_title=None, fee=None):
    return SimpleNamespace(
        symbol=symbol,
        market=SimpleNamespace(price_usd=price, change_24h_pct=change_pct) if price is not None else None,
        fear_greed=SimpleNamespace(value=fg_value, classification=fg_class) if fg_class is not None else None,
        top_news=SimpleNamespace(title=news_title) if news_title is not None else None,
        fees=SimpleNamespace(fastest_sat_vb=fee) if fee is not None else None,
    )


class TestInitialize:
    def test_creates_database_file_automatically(self, tmp_path) -> None:
        db_path = str(tmp_path / "auto_created.db")
        assert not os.path.exists(db_path)

        store = SQLiteSnapshotStore(db_path)
        store.initialize()

        assert os.path.exists(db_path)
        store.close()

    def test_idempotent_when_called_twice(self, tmp_path) -> None:
        db_path = str(tmp_path / "idempotent.db")
        store = SQLiteSnapshotStore(db_path)
        store.initialize()
        store.initialize()
        store.close()

    def test_memory_backend_works_without_a_file(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        assert store.get_latest("BTC") is None
        store.close()


class TestEmptyLookup:
    def test_get_latest_returns_none_when_absent(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        assert store.get_latest("ETH") is None
        store.close()


class TestInsertAndUpsert:
    def test_save_snapshot_then_get_latest_roundtrips(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        snapshot = _fake_snapshot(
            symbol="BTC", price=64000.0, change_pct=-1.5, fg_value=30,
            fg_class="Fear", news_title="Some headline", fee=15.0,
        )

        store.save_snapshot(snapshot)
        record = store.get_latest("BTC")

        assert record is not None
        assert record.symbol == "BTC"
        assert record.price_usd == 64000.0
        assert record.change_24h_pct == -1.5
        assert record.fear_greed_value == 30
        assert record.fear_greed_classification == "Fear"
        assert record.top_news_title == "Some headline"
        assert record.fees_fastest_sat_vb == 15.0
        assert record.captured_at
        store.close()

    def test_save_snapshot_upserts_same_symbol(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()

        store.save_snapshot(_fake_snapshot(symbol="BTC", price=64000.0))
        store.save_snapshot(_fake_snapshot(symbol="BTC", price=65000.0))

        record = store.get_latest("BTC")
        assert record.price_usd == 65000.0
        assert store.count_tracked_symbols() == 1
        store.close()

    def test_different_symbols_are_isolated(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()

        store.save_snapshot(_fake_snapshot(symbol="BTC", price=64000.0))
        store.save_snapshot(_fake_snapshot(symbol="ETH", price=3000.0))

        assert store.get_latest("BTC").price_usd == 64000.0
        assert store.get_latest("ETH").price_usd == 3000.0
        store.close()

    def test_symbol_lookup_is_case_insensitive(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        store.save_snapshot(_fake_snapshot(symbol="BTC", price=64000.0))
        assert store.get_latest("btc").price_usd == 64000.0
        store.close()


class TestNullFields:
    def test_missing_optional_fields_stored_as_none(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        snapshot = _fake_snapshot(symbol="SOL", price=150.0)

        store.save_snapshot(snapshot)
        record = store.get_latest("SOL")

        assert record.price_usd == 150.0
        assert record.fear_greed_value is None
        assert record.fear_greed_classification is None
        assert record.top_news_title is None
        assert record.fees_fastest_sat_vb is None
        store.close()

    def test_missing_market_stores_none_price(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        store.initialize()
        snapshot = _fake_snapshot(symbol="DOGE")

        store.save_snapshot(snapshot)
        record = store.get_latest("DOGE")

        assert record.price_usd is None
        assert record.change_24h_pct is None
        store.close()


class TestPersistenceAcrossRestart:
    def test_data_survives_reopening_the_same_file(self, tmp_path) -> None:
        db_path = str(tmp_path / "snapshot_persist.db")

        store1 = SQLiteSnapshotStore(db_path)
        store1.initialize()
        store1.save_snapshot(_fake_snapshot(symbol="BTC", price=64000.0, fg_class="Fear"))
        store1.close()

        store2 = SQLiteSnapshotStore(db_path)
        store2.initialize()
        record = store2.get_latest("BTC")

        assert record is not None
        assert record.price_usd == 64000.0
        assert record.fear_greed_classification == "Fear"
        store2.close()


class TestHealthCheck:
    def test_reports_availability_and_path(self, tmp_path) -> None:
        db_path = str(tmp_path / "health.db")
        store = SQLiteSnapshotStore(db_path)
        store.initialize()
        store.save_snapshot(_fake_snapshot(symbol="BTC", price=64000.0))

        health = store.health_check()

        assert health["status"] == "healthy"
        assert health["backend"] == "sqlite"
        assert health["database_available"] is True
        assert health["database_path"] == db_path
        assert health["tracked_symbols"] == 1
        store.close()


class TestUninitializedUse:
    def test_using_store_before_initialize_raises(self) -> None:
        store = SQLiteSnapshotStore(":memory:")
        with pytest.raises(RuntimeError):
            store.get_latest("BTC")
