"""AlertService — orchestrates one full alert-detection cycle across every
watched symbol (TASK-023 Phase G). Deterministic only: detect_changes()
supplies the change strings, this module only formats them into a
Telegram message and handles delivery/cooldown/persistence around them.
No AI involvement anywhere in this pipeline.

Primary deduplication defense is the advancing snapshot baseline (each
cycle compares against the immediately preceding snapshot via
snapshot_store, then always overwrites it — save_snapshot() runs on
every successful fetch, changed or not). The cooldown store is a
secondary defense only, against flapping within a short window.
"""
from typing import Any, Dict, List

from phoenix_core.services.research.change_detection import detect_changes
from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_COOLDOWN_SECONDS = 1800.0

# Maps the fixed emoji prefixes documented in change_detection.py's
# returned strings to a stable category name for cooldown fingerprinting.
# Parses the public return contract only — never reaches into
# change_detection's private helpers.
_CATEGORY_PREFIXES = {
    "\U0001F4B0": "price",
    "\U0001F628": "sentiment",
    "\U0001F4F0": "news",
    "\u26FD": "fee",
}


def _categorize(change_text: str) -> str:
    for prefix, category in _CATEGORY_PREFIXES.items():
        if change_text.startswith(prefix):
            return category
    return "other"


def _format_alert(symbol: str, changes: List[str]) -> str:
    """Build the Telegram alert text from already-generated change strings.
    Purely deterministic — no AI, no reinterpretation of the change text."""
    lines = [f"\U0001F6A8 Промяна при {symbol}", ""]
    lines.extend(changes)
    return "\n".join(lines)


class AlertService:
    """Runs one detection+delivery cycle across every symbol on any watchlist."""

    def __init__(
        self,
        aggregator,
        snapshot_store,
        cooldown_store,
        watchlist_manager,
        notification_service,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._aggregator = aggregator
        self._snapshot_store = snapshot_store
        self._cooldown_store = cooldown_store
        self._watchlist_manager = watchlist_manager
        self._notification_service = notification_service
        self._cooldown_seconds = cooldown_seconds

    async def run_cycle(self) -> Dict[str, Any]:
        """Process every currently watched symbol once. Never raises —
        a failure processing one symbol is logged and skipped so the rest
        of the cycle still runs. Returns a small stats dict, mainly for
        tests and diagnostics."""
        symbols = self._watchlist_manager.list_all_symbols()
        stats: Dict[str, Any] = {"symbols_processed": 0, "alerts_sent": 0, "symbols_skipped": 0}

        for symbol in symbols:
            try:
                sent = await self._process_symbol(symbol)
                stats["symbols_processed"] += 1
                stats["alerts_sent"] += sent
            except Exception as e:
                stats["symbols_skipped"] += 1
                logger.error(
                    "Alert cycle failed for symbol",
                    symbol=symbol,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        return stats

    async def _process_symbol(self, symbol: str) -> int:
        """Process one symbol end-to-end. Returns the number of users
        successfully notified (0 if no change, no watchers, or suppressed)."""
        current = await self._aggregator.get_snapshot(symbol)

        if current.is_empty:
            logger.warning("Market intelligence unavailable, skipping symbol", symbol=symbol)
            return 0

        previous_row = self._snapshot_store.get_latest(symbol)
        changes = detect_changes(previous_row, current)

        # Advancing baseline: always persist the new snapshot, changed or not —
        # this is what stops the same movement from re-alerting every cycle.
        self._snapshot_store.save_snapshot(current)

        if not changes:
            return 0

        categories = [_categorize(c) for c in changes]

        if not self._cooldown_store.should_alert(symbol, categories, self._cooldown_seconds):
            logger.info("Alert suppressed by cooldown", symbol=symbol, categories=categories)
            return 0

        watchers = self._watchlist_manager.list_watchers(symbol)
        if not watchers:
            return 0

        alert_text = _format_alert(current.symbol, changes)

        sent_count = 0
        for user_id in watchers:
            try:
                success = await self._notification_service.send(user_id, alert_text)
                if success:
                    sent_count += 1
            except Exception as e:
                # Defense in depth: NotificationService.send() is contracted
                # to return False rather than raise, but a single unexpected
                # exception here must still never abort the rest of the loop.
                logger.warning(
                    "Unexpected notification error", symbol=symbol, user_id=user_id, error=str(e)
                )

        self._cooldown_store.record_alert(symbol, categories)
        return sent_count
