"""Unit tests for phoenix_core.services.crypto.cache.TTLCache."""
import time
import pytest
from phoenix_core.services.crypto.cache import TTLCache


class TestConstruction:
    def test_non_positive_ttl_rejected(self) -> None:
        with pytest.raises(ValueError):
            TTLCache(ttl_seconds=0)


class TestGetSet:
    def test_missing_key_returns_none(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("missing") is None

    def test_set_then_get_returns_value(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        cache.set("btc", {"price": 100})
        assert cache.get("btc") == {"price": 100}

    def test_len_reflects_stored_entries(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2


class TestExpiry:
    def test_entry_expires_after_ttl(self) -> None:
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("btc", 100)
        assert cache.get("btc") == 100
        time.sleep(0.1)
        assert cache.get("btc") is None

    def test_expired_entry_is_removed_from_store(self) -> None:
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("btc", 100)
        time.sleep(0.1)
        cache.get("btc")
        assert len(cache) == 0


class TestClear:
    def test_clear_removes_all_entries(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None
