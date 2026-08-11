"""Unit tests for AlertScheduler (TASK-023 Phase G)."""
import asyncio

import pytest

from phoenix_core.services.research.alert_scheduler import AlertScheduler


class FakeAlertService:
    def __init__(self, delay: float = 0.0, raise_error: bool = False) -> None:
        self.delay = delay
        self.raise_error = raise_error
        self.calls = 0

    async def run_cycle(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_error:
            raise RuntimeError("boom")
        return {"symbols_processed": 1, "alerts_sent": 0, "symbols_skipped": 0}


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_then_stop_cleanly(self) -> None:
        service = FakeAlertService()
        scheduler = AlertScheduler(service, interval_seconds=100)

        await scheduler.start()
        health = await scheduler.health_check()
        assert health["status"] == "healthy"

        await scheduler.stop()
        health = await scheduler.health_check()
        assert health["status"] == "not_started"

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        service = FakeAlertService()
        scheduler = AlertScheduler(service, interval_seconds=100)

        await scheduler.start()
        await scheduler.start()  # must not raise or spawn a second task

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_before_start_is_a_noop(self) -> None:
        service = FakeAlertService()
        scheduler = AlertScheduler(service, interval_seconds=100)
        await scheduler.stop()  # must not raise


class TestCycleExecution:
    @pytest.mark.asyncio
    async def test_cycle_runs_after_interval_elapses(self) -> None:
        service = FakeAlertService()
        scheduler = AlertScheduler(service, interval_seconds=0.01)

        await scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert service.calls >= 1

    @pytest.mark.asyncio
    async def test_cycle_exception_does_not_kill_scheduler(self) -> None:
        service = FakeAlertService(raise_error=True)
        scheduler = AlertScheduler(service, interval_seconds=0.01)

        await scheduler.start()
        await asyncio.sleep(0.05)
        health = await scheduler.health_check()
        await scheduler.stop()

        assert health["status"] == "healthy"  # loop survived the raised exception


class TestOverlappingCycleGuard:
    """The scheduler's single-task loop makes overlap structurally
    impossible: sleep() for the next tick never begins until the current
    cycle has fully returned, so run_cycle() calls can never interleave.
    These tests verify that guarantee directly, plus that the guard
    counter/flag stay well-defined (never left "stuck" as in-progress)
    even when a cycle is slow."""

    @pytest.mark.asyncio
    async def test_slow_cycle_never_overlaps_with_the_next_one(self) -> None:
        service = FakeAlertService(delay=0.05)
        scheduler = AlertScheduler(service, interval_seconds=0.01)

        await scheduler.start()
        await asyncio.sleep(0.17)
        health = await scheduler.health_check()
        await scheduler.stop()

        # Sequential-only execution: no overlap ever occurs, so the guard
        # counter -- which only increments on a genuine overlap -- stays at 0.
        assert health["cycles_skipped_overlap"] == 0
        # ~0.17s of runtime with a 0.05s cycle + 0.01s interval allows at
        # most a couple of full cycles, never more than the loop can
        # sequentially fit.
        assert service.calls <= 3

    @pytest.mark.asyncio
    async def test_cycle_in_progress_flag_is_cleared_after_a_slow_cycle(self) -> None:
        service = FakeAlertService(delay=0.03)
        scheduler = AlertScheduler(service, interval_seconds=0.01)

        await scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        # If the flag were left stuck "in progress", every subsequent tick
        # would show up as a skipped overlap -- confirm that never happens.
        health = await scheduler.health_check()
        assert health["cycles_skipped_overlap"] == 0
