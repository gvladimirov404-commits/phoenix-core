"""AlertScheduler — periodic background driver for AlertService (TASK-023
Phase G). A lifecycle component (start()/stop()/health_check()) that
PhoenixApplication manages exactly like every other component in
self._components — no changes to PhoenixApplication.start() itself were
needed.

Runs AlertService.run_cycle() on a fixed interval via an internal
asyncio task. Guards against overlapping cycles (if a cycle is still
running when the next tick fires, the tick is skipped and logged rather
than run concurrently). A cycle raising is caught and logged so a bad
cycle never kills the scheduler loop itself — AlertService already
isolates per-symbol failures, this is the outer safety net.
"""
import asyncio
from typing import Any, Dict, Optional

from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)


class AlertScheduler:
    """Periodically runs AlertService.run_cycle() every `interval_seconds`."""

    def __init__(self, alert_service, interval_seconds: float = 300.0) -> None:
        self._alert_service = alert_service
        self._interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._cycle_in_progress = False
        self._cycles_run = 0
        self._cycles_skipped_overlap = 0

    async def start(self) -> None:
        """Start the background polling loop (idempotent)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Alert scheduler started", interval_seconds=self._interval_seconds)

    async def stop(self) -> None:
        """Stop the background loop and wait for it to exit cleanly."""
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Alert scheduler stopped")

    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if self._running else "not_started",
            "interval_seconds": self._interval_seconds,
            "cycles_run": self._cycles_run,
            "cycles_skipped_overlap": self._cycles_skipped_overlap,
        }

    async def _loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval_seconds)
                if not self._running:
                    break
                await self._run_cycle_guarded()
        except asyncio.CancelledError:
            raise

    async def _run_cycle_guarded(self) -> None:
        if self._cycle_in_progress:
            self._cycles_skipped_overlap += 1
            logger.warning("Alert cycle still running, skipping this tick")
            return

        self._cycle_in_progress = True
        try:
            stats = await self._alert_service.run_cycle()
            self._cycles_run += 1
            logger.info("Alert cycle completed", **stats)
        except Exception as e:
            logger.error("Alert cycle raised an unexpected error", error=str(e), error_type=type(e).__name__)
        finally:
            self._cycle_in_progress = False
