"""Unit tests for WatchlistManager (Task 020, /watch) — real in-memory SQLite,
no mocking needed, mirroring test_conversation_manager.py's approach."""
import pytest

from phoenix_core.services.watchlist.manager import WatchlistManager


class TestWatchlistManager:
    def test_new_user_has_empty_watchlist(self) -> None:
        manager = WatchlistManager()
        assert manager.get_watchlist(1) == []

    def test_add_symbols_persists_and_normalizes_case(self) -> None:
        manager = WatchlistManager()
        result = manager.add_symbols(1, ["btc", "ETH", " sol "])
        assert result == ["BTC", "ETH", "SOL"]
        assert manager.get_watchlist(1) == ["BTC", "ETH", "SOL"]

    def test_duplicate_symbols_are_deduplicated(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])
        result = manager.add_symbols(1, ["btc", "eth"])
        assert result == ["BTC", "ETH"]

    def test_watchlists_are_isolated_per_user(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])
        manager.add_symbols(2, ["eth"])
        assert manager.get_watchlist(1) == ["BTC"]
        assert manager.get_watchlist(2) == ["ETH"]

    def test_clear_removes_all_symbols(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc", "eth"])
        deleted = manager.clear(1)
        assert deleted == 2
        assert manager.get_watchlist(1) == []

    def test_watchlist_survives_across_manager_instances_with_same_db_path(self, tmp_path) -> None:
        db_path = str(tmp_path / "watchlist_test.db")
        manager_a = WatchlistManager(db_path=db_path)
        manager_a.add_symbols(1, ["btc"])

        manager_b = WatchlistManager(db_path=db_path)
        assert manager_b.get_watchlist(1) == ["BTC"]

    @pytest.mark.asyncio
    async def test_health_check_reports_status(self) -> None:
        manager = WatchlistManager()
        health = await manager.health_check()
        assert health["status"] == "healthy"
        assert health["backend"] == "sqlite"

    @pytest.mark.asyncio
    async def test_stop_closes_store_cleanly(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])
        await manager.stop()  # must not raise


class TestListWatchersAndAllSymbols:
    """Tests for the read-only reverse-lookup extensions (Task 023 Phase G)."""

    def test_list_watchers_returns_users_watching_symbol(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])
        manager.add_symbols(2, ["btc", "eth"])

        watchers = manager.list_watchers("BTC")

        assert set(watchers) == {1, 2}

    def test_list_watchers_returns_empty_when_nobody_watches(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])

        assert manager.list_watchers("SOL") == []

    def test_list_watchers_is_case_insensitive(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc"])

        assert manager.list_watchers("btc") == [1]

    def test_list_all_symbols_deduplicates_across_users(self) -> None:
        manager = WatchlistManager()
        manager.add_symbols(1, ["btc", "eth"])
        manager.add_symbols(2, ["btc", "sol"])

        symbols = manager.list_all_symbols()

        assert set(symbols) == {"BTC", "ETH", "SOL"}

    def test_list_all_symbols_empty_when_no_watchlists(self) -> None:
        manager = WatchlistManager()
        assert manager.list_all_symbols() == []
