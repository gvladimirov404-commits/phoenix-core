"""Unit tests for AlertService (TASK-023 Phase G) — pure fakes, no real
SQLite or Telegram involved; exercises the orchestration logic only."""
from types import SimpleNamespace

import pytest

from phoenix_core.services.research.alert_service import AlertService
from phoenix_core.services.research.snapshot_store import SnapshotRecord


def _snapshot(symbol="BTC", price=None, fg_class=None, news_title=None, fee=None, empty=False):
    if empty:
        return SimpleNamespace(symbol=symbol, market=None, fear_greed=None, top_news=None, fees=None, is_empty=True)
    return SimpleNamespace(
        symbol=symbol,
        market=SimpleNamespace(price_usd=price, change_24h_pct=None) if price is not None else None,
        fear_greed=SimpleNamespace(value=None, classification=fg_class) if fg_class is not None else None,
        top_news=SimpleNamespace(title=news_title) if news_title is not None else None,
        fees=SimpleNamespace(fastest_sat_vb=fee) if fee is not None else None,
        is_empty=False,
    )


def _record(price=None, fg_class=None, news_title=None, fee=None):
    return SnapshotRecord(
        symbol="BTC", price_usd=price, change_24h_pct=None,
        fear_greed_value=None, fear_greed_classification=fg_class,
        top_news_title=news_title, fees_fastest_sat_vb=fee,
        captured_at="2026-01-01T00:00:00+00:00",
    )


class FakeAggregator:
    def __init__(self, snapshots: dict) -> None:
        self._snapshots = snapshots

    async def get_snapshot(self, symbol):
        return self._snapshots[symbol]


class FakeSnapshotStore:
    def __init__(self, previous: dict | None = None) -> None:
        self._previous = previous or {}
        self.saved = []

    def get_latest(self, symbol):
        return self._previous.get(symbol)

    def save_snapshot(self, snapshot):
        self.saved.append(snapshot.symbol)


class FakeCooldownStore:
    def __init__(self, suppress: bool = False) -> None:
        self.suppress = suppress
        self.recorded = []

    def should_alert(self, symbol, categories, cooldown_seconds):
        return not self.suppress

    def record_alert(self, symbol, categories):
        self.recorded.append((symbol, tuple(sorted(categories))))


class FakeWatchlistManager:
    def __init__(self, symbols, watchers: dict) -> None:
        self._symbols = symbols
        self._watchers = watchers

    def list_all_symbols(self):
        return self._symbols

    def list_watchers(self, symbol):
        return self._watchers.get(symbol, [])


class FakeNotificationService:
    def __init__(self, fail_for: set | None = None) -> None:
        self.fail_for = fail_for or set()
        self.sent = []

    async def send(self, user_id, text):
        if user_id in self.fail_for:
            return False
        self.sent.append((user_id, text))
        return True


def _make_service(aggregator, snapshot_store, cooldown_store, watchlist_manager, notification_service):
    return AlertService(
        aggregator=aggregator,
        snapshot_store=snapshot_store,
        cooldown_store=cooldown_store,
        watchlist_manager=watchlist_manager,
        notification_service=notification_service,
        cooldown_seconds=1800,
    )


class TestFirstSnapshotNoAlert:
    @pytest.mark.asyncio
    async def test_no_previous_snapshot_means_no_alert_but_saves(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=100.0)})
        snapshot_store = FakeSnapshotStore(previous={})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 0
        assert snapshot_store.saved == ["BTC"]
        assert notifier.sent == []


class TestNormalChangeAlert:
    @pytest.mark.asyncio
    async def test_price_change_above_threshold_sends_alert(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=110.0)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1, 2]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 2
        assert len(notifier.sent) == 2
        assert cooldown_store.recorded == [("BTC", ("price",))]


class TestNoChangeNoAlert:
    @pytest.mark.asyncio
    async def test_unchanged_price_sends_nothing(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=100.5)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 0
        assert notifier.sent == []


class TestMultipleChangesOneAlert:
    @pytest.mark.asyncio
    async def test_multiple_changes_produce_a_single_coherent_message(self) -> None:
        aggregator = FakeAggregator({
            "BTC": _snapshot(price=110.0, fg_class="Greed", news_title="New headline")
        })
        snapshot_store = FakeSnapshotStore(previous={
            "BTC": _record(price=100.0, fg_class="Fear", news_title="Old headline")
        })
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        await service.run_cycle()

        assert len(notifier.sent) == 1
        user_id, text = notifier.sent[0]
        assert "нагоре" in text
        assert "Fear" in text and "Greed" in text
        assert "New headline" in text


class TestCooldownSuppression:
    @pytest.mark.asyncio
    async def test_suppressed_when_cooldown_active(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=110.0)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore(suppress=True)
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 0
        assert notifier.sent == []
        # snapshot still advances even when the alert itself is suppressed
        assert snapshot_store.saved == ["BTC"]


class TestZeroWatchers:
    @pytest.mark.asyncio
    async def test_change_with_no_watchers_sends_nothing(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=110.0)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": []})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 0


class TestMultipleWatchers:
    @pytest.mark.asyncio
    async def test_all_watchers_receive_the_alert(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=110.0)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1, 2, 3]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 3


class TestOneFailedDelivery:
    @pytest.mark.asyncio
    async def test_one_failed_user_does_not_block_others(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(price=110.0)})
        snapshot_store = FakeSnapshotStore(previous={"BTC": _record(price=100.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1, 2]})
        notifier = FakeNotificationService(fail_for={1})

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["alerts_sent"] == 1
        assert notifier.sent == [(2, notifier.sent[0][1])]


class TestProviderFailure:
    @pytest.mark.asyncio
    async def test_empty_snapshot_skips_symbol_without_crashing(self) -> None:
        aggregator = FakeAggregator({"BTC": _snapshot(empty=True)})
        snapshot_store = FakeSnapshotStore(previous={})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC"], {"BTC": [1]})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["symbols_skipped"] == 0  # handled gracefully, not an error path
        assert stats["alerts_sent"] == 0
        assert snapshot_store.saved == []  # never saved an empty snapshot


class TestNoWatchedSymbols:
    @pytest.mark.asyncio
    async def test_zero_symbols_is_a_clean_noop(self) -> None:
        aggregator = FakeAggregator({})
        snapshot_store = FakeSnapshotStore()
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager([], {})
        notifier = FakeNotificationService()

        service = _make_service(aggregator, snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats == {"symbols_processed": 0, "alerts_sent": 0, "symbols_skipped": 0}


class TestSymbolLevelExceptionIsolation:
    @pytest.mark.asyncio
    async def test_exception_for_one_symbol_does_not_abort_cycle(self) -> None:
        class ExplodingAggregator:
            async def get_snapshot(self, symbol):
                if symbol == "BTC":
                    raise RuntimeError("boom")
                return _snapshot(symbol=symbol, price=100.0)

        snapshot_store = FakeSnapshotStore(previous={"ETH": _record(price=90.0)})
        cooldown_store = FakeCooldownStore()
        watchlist = FakeWatchlistManager(["BTC", "ETH"], {"ETH": [1]})
        notifier = FakeNotificationService()

        service = _make_service(ExplodingAggregator(), snapshot_store, cooldown_store, watchlist, notifier)
        stats = await service.run_cycle()

        assert stats["symbols_skipped"] == 1
        assert stats["symbols_processed"] == 1
