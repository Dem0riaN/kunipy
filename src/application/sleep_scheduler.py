"""Sleep scheduler for diary consolidation.

Handles nightly sleep consolidation ("Kuni requires sleep, as a human does").
Extracted from app.py god object (ТЗ-001 punkt 5).
"""

import asyncio
import logging
from datetime import datetime, timedelta

from ..di import Dependencies

logger = logging.getLogger(__name__)


class SleepScheduler:
    """Manages sleep consolidation schedule.

    Responsibilities:
    1. Schedule nightly diary consolidation
    2. Run at optimal time (quiet night hours)
    3. Auto-trigger based on ТЗ-001 punkt 19

    Based on C++ kuni sleep consolidation pattern.
    """

    def __init__(self, deps: Dependencies, night_hour: int = 4):
        """Initialize sleep scheduler.

        Args:
            deps: Dependency injection container
            night_hour: Hour to run consolidation (default 4 AM)
        """
        self._deps = deps
        self._night_hour = night_hour
        self._running = False
        self._task: asyncio.Task = None

    async def start(self) -> None:
        """Start sleep consolidation loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._sleep_loop(), name="sleep-scheduler")
        logger.info(f"Sleep scheduler started (runs at {self._night_hour}:00 AM)")

    async def stop(self) -> None:
        """Stop sleep consolidation loop."""
        if not self._running:
            return

        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Sleep scheduler stopped")

    async def _sleep_loop(self) -> None:
        """Background loop that runs consolidation once a day.

        Mirrors original kuni's "Kuni requires sleep, as a human does" behavior.
        """
        if not self._deps.diary:
            logger.warning("Diary not available, sleep consolidation disabled")
            return

        logger.info("Sleep consolidation loop started")

        while self._running:
            try:
                # Calculate next run time
                now = datetime.now()
                next_run = now.replace(
                    hour=self._night_hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )

                # If already past today's run time, schedule for tomorrow
                if next_run <= now:
                    next_run += timedelta(days=1)

                # Wait until next run
                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"Next sleep consolidation at {next_run} ({sleep_seconds/3600:.1f}h)")
                await asyncio.sleep(sleep_seconds)

                if not self._running:
                    break

                # Run consolidation
                logger.info("Starting nightly diary sleep consolidation")
                await self._run_consolidation()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Sleep consolidation loop error: {e}")
                # Back off an hour on unexpected errors
                await asyncio.sleep(3600)

    async def _run_consolidation(self) -> None:
        """Run sleep consolidation.

        Implements ТЗ-001 punkt 19: auto-trigger sleep consolidation.
        """
        try:
            await self._deps.diary.sleep_consolidation()
            logger.info("Sleep consolidation completed successfully")
        except Exception as e:
            logger.error(f"Sleep consolidation failed: {e}")

    async def trigger_manual_consolidation(self) -> None:
        """Manually trigger consolidation (for testing/debugging)."""
        logger.info("Manual sleep consolidation triggered")
        await self._run_consolidation()
