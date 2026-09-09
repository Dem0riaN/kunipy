"""Worker orchestration for notification handling.

This module coordinates the worker pool that processes notifications from the
notification manager. Each worker runs in its own asyncio task and pulls
notifications from a shared queue.
"""

import asyncio
import logging
from typing import List

from ..notification_manager import Notification
from ..interfaces.worker import INotificationManager

logger = logging.getLogger(__name__)


class WorkerOrchestrator:
    """Orchestrates worker tasks for notification processing.

    Responsibilities:
    - Start worker tasks in background
    - Manage worker lifecycle (start/stop)
    - Wake up sleeping workers when high-priority notifications arrive
    """

    def __init__(
        self,
        notification_manager: INotificationManager,
        workers: List,  # List[Worker] - avoid circular import
    ) -> None:
        """Initialize orchestrator.

        Args:
            notification_manager: Manager for notification queue
            workers: List of worker instances to orchestrate
        """
        self._notification_manager = notification_manager
        self._workers = workers
        self._tasks: List[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start all worker tasks."""
        if self._running:
            logger.warning("WorkerOrchestrator already running")
            return

        self._running = True
        logger.info(f"Starting {len(self._workers)} workers")

        # Create task for each worker
        for worker in self._workers:
            task = asyncio.create_task(
                worker.run(),
                name=f"worker-{worker.name}"
            )
            self._tasks.append(task)

        logger.info("All workers started")

    async def stop(self) -> None:
        """Stop all worker tasks and dump remaining context."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping workers...")

        # Cancel all worker tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Clear temporary context from each worker
        # (diary dumping happens in App.stop to access diary instance)
        for worker in self._workers:
            worker.temporary_context = {}

        self._tasks.clear()
        logger.info("Workers stopped")

    def wake_up_all(self) -> None:
        """Wake up all sleeping workers (e.g., for high-priority notifications)."""
        for worker in self._workers:
            worker.wake_up()

    @property
    def workers(self) -> List:
        """Access to worker list for external coordination."""
        return self._workers
