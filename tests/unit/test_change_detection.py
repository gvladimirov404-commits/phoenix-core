"""Unit tests for phoenix_core.services.research.change_detection."""
from types import SimpleNamespace

from phoenix_core.services.research.change_detection import detect_changes
from phoenix_core.services.research.snapshot_store import SnapshotRecord


def _snapshot(price=None, change_pct=None, fg_value=None, fg_class=None,
              news_title=None, fee=None):
    return SimpleNamespace(
        market=SimpleNamespace(price_usd=price, change_24h_pct=change_pct) if price is not None else None,
        fear_greed=SimpleNamespace(value=fg_value, classification=fg_class) if fg_class is not None else None,
        top_news=SimpleNamespace(title=news_title) if news_title is not None else None,
        fees=SimpleNamespace(fastest_sat_vb=fee) if fee is not None else None,
    )


def _record(price=None, fg_class=None, news_title=None, fee=None):
    return SnapshotRecord(
        symbol="BTC",
        price_usd=price,
        change_24h_pct=None,
        fear_greed_value=None,
        fear_greed_classification=fg_class,
        top_news_title=news_title,
        fees_fastest_sat_vb=fee,
        captured_at="2026-01-01T00:00:00+00:00",
    )


class TestNoPreviousSnapshot:
    def test_returns_empty_list_when_no_previous_row(self) -> None:
        current = _snapshot(price=100.0)
        assert detect_changes(None, current) == []


class TestNoChanges:
    def test_returns_empty_list_when_nothing_changed(self) -> None:
        previous = _record(price=100.0, fg_class="Neutral", news_title="Same headline", fee=10.0)
        current = _snapshot(price=100.5, fg_class="Neutral", news_title="Same headline", fee=10.5)
        assert detect_changes(previous, current) == []


class TestPriceChange:
    def test_price_increase_above_threshold_detected(self) -> None:
        previous = _record(price=100.0)
        current = _snapshot(price=104.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "нагоре" in changes[0]
        assert "100.00" in changes[0] and "104.00" in changes[0]

    def test_price_decrease_below_threshold_detected(self) -> None:
        previous = _record(price=100.0)
        current = _snapshot(price=96.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "надолу" in changes[0]

    def test_price_change_within_threshold_not_detected(self) -> None:
        previous = _record(price=100.0)
        current = _snapshot(price=102.0)
        assert detect_changes(previous, current) == []

    def test_price_change_exactly_at_threshold_boundary(self) -> None:
        previous = _record(price=100.0)
        current = _snapshot(price=103.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 1

    def test_previous_price_zero_does_not_crash(self) -> None:
        previous = _record(price=0.0)
        current = _snapshot(price=10.0)
        assert detect_changes(previous, current) == []


class TestSentimentChange:
    def test_fear_greed_category_change_detected(self) -> None:
        previous = _record(fg_class="Fear")
        current = _snapshot(fg_class="Greed")
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "Fear" in changes[0] and "Greed" in changes[0]

    def test_fear_greed_same_category_not_detected(self) -> None:
        previous = _record(fg_class="Neutral")
        current = _snapshot(fg_class="Neutral")
        assert detect_changes(previous, current) == []


class TestNewsChange:
    def test_new_top_news_title_detected(self) -> None:
        previous = _record(news_title="Old headline")
        current = _snapshot(news_title="New headline")
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "New headline" in changes[0]

    def test_same_top_news_title_not_detected(self) -> None:
        previous = _record(news_title="Same headline")
        current = _snapshot(news_title="Same headline")
        assert detect_changes(previous, current) == []


class TestFeeSpike:
    def test_fee_spike_upward_detected(self) -> None:
        previous = _record(fee=10.0)
        current = _snapshot(fee=35.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "скочиха" in changes[0]

    def test_fee_drop_detected(self) -> None:
        previous = _record(fee=50.0)
        current = _snapshot(fee=20.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 1
        assert "спаднаха" in changes[0]

    def test_fee_change_within_threshold_not_detected(self) -> None:
        previous = _record(fee=10.0)
        current = _snapshot(fee=25.0)
        assert detect_changes(previous, current) == []


class TestMultipleChanges:
    def test_multiple_simultaneous_changes_all_reported(self) -> None:
        previous = _record(price=100.0, fg_class="Fear", news_title="Old", fee=10.0)
        current = _snapshot(price=110.0, fg_class="Greed", news_title="New", fee=40.0)
        changes = detect_changes(previous, current)
        assert len(changes) == 4


class TestMissingData:
    def test_missing_current_market_does_not_crash(self) -> None:
        previous = _record(price=100.0)
        current = _snapshot()
        assert detect_changes(previous, current) == []

    def test_missing_previous_price_skips_price_check(self) -> None:
        previous = _record()
        current = _snapshot(price=100.0)
        assert detect_changes(previous, current) == []
