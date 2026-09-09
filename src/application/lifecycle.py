"""Application lifecycle management.

Handles startup, shutdown, and component initialization.
Extracted from app.py god object (ТЗ-001 punkt 5).
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from ..di import Dependencies

logger = logging.getLogger(__name__)


class ApplicationLifecycle:
    """Manages application startup and shutdown.

    Responsibilities:
    1. Initialize all components via DI
    2. Start background tasks (workers, proxy, metrics)
    3. Graceful shutdown
    4. Task lifecycle management

    Based on C++ kuni AppBase lifecycle pattern.
    """

    def __init__(self, deps: Dependencies, working_dir: Path):
        """Initialize lifecycle manager.

        Args:
            deps: Dependency injection container
            working_dir: Application working directory
        """
        self._deps = deps
        self._working_dir = working_dir
        self._running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        """Start the application.

        Startup sequence:
        1. Load working memory from disk
        2. Start notification manager
        3. Start workers
        4. Send startup notifications (if Telegram enabled)
        5. Start background loops (proactive, sleep, metrics)
        6. Start proxy server (if enabled)
        """
        if self._running:
            logger.warning("Application already running")
            return

        self._running = True
        logger.info("Starting kunipy application...")

        # Restore working memory from previous session
        from ..working_memory import get_working_memory
        get_working_memory().load_from_file()

        # Start notification manager
        worker_count = max(1, self._deps.config.worker_count)
        self._deps.notification_manager.start(worker_count)

        logger.info(f"Application started with {worker_count} workers")

    async def stop(self) -> None:
        """Stop the application gracefully.

        Shutdown sequence:
        1. Save working memory to disk
        2. Cancel all background tasks
        3. Stop notification manager
        4. Stop Telegram client
        5. Dump remaining context to diary
        """
        if not self._running:
            return

        self._running = False
        logger.info("Stopping application...")

        # Persist working memory
        from ..working_memory import get_working_memory
        get_working_memory().save_to_file()

        # Cancel all background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        # Stop notification manager
        await self._deps.notification_manager.stop()

        # Stop Telegram client
        if self._deps.telegram_client:
            await self._deps.telegram_client.stop()

        logger.info("Application stopped")

    def is_running(self) -> bool:
        """Check if application is running."""
        return self._running

    def add_background_task(self, coro, name: str) -> asyncio.Task:
        """Add a background task to be managed by lifecycle.

        Args:
            coro: Coroutine to run
            name: Task name for logging

        Returns:
            Created task
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.append(task)
        return task

    async def wait_for_shutdown(self) -> None:
        """Block until application is shut down.

        Waits for all background tasks to complete or KeyboardInterrupt.
        """
        try:
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
        finally:
            await self.stop()
