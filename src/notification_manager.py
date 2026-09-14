"""Notification manager for kunipy.

Handles a priority queue of notifications and dispatches them to workers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """A notification representing an incoming event (message, etc.)."""

    _id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 0  # higher = more urgent
    message: str = ""
    pin: str = ""  # grouping key (e.g., chat_id)
    actions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: Notification) -> bool:
        # For heapq: lower priority number = higher urgency (we invert)
        return self.priority > other.priority


class NotificationManager:
    """Manages a priority queue of notifications and dispatches them.

    Workers pull from this queue. Notifications are processed in order
    of priority (highest first).
    """

    def __init__(self, max_queue_size: int = 1000):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(max_queue_size)
        self._running = False
        self._handlers: list[Callable[[Notification], None]] = []
        self._worker_count = 0
        self._tasks: list[asyncio.Task] = []

    def register_handler(self, handler: Callable[[Notification], None]) -> None:
        """Register a handler that will be called when a notification is popped."""
        self._handlers.append(handler)

    def start(self, worker_count: int) -> None:
        """Start the notification manager (workers will pull from queue)."""
        self._worker_count = worker_count
        self._running = True
        logger.info(f"Notification manager started with {worker_count} workers")
        # Workers are started externally; we just keep the queue.

    async def stop(self) -> None:
        """Stop the notification manager."""
        self._running = False
        # Cancel worker tasks if any
        for task in self._tasks:
            if not task.done():
                task.cancel()
        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Notification manager stopped")

    def add_notification(self, notification: Notification) -> None:
        """Add a notification to the queue."""
        if not self._running:
            logger.warning("Notification manager not running, dropping notification")
            return
        try:
            # PriorityQueue expects (priority, item) where priority is lower = higher
            # We invert priority so higher number = higher urgency
            self._queue.put_nowait((-notification.priority, notification))
            logger.info(f"Added notification {notification._id} with priority {notification.priority}, queue_size={self._queue.qsize()}")
        except asyncio.QueueFull:
            logger.warning("Notification queue full, dropping notification")

    async def pass_notification(
        self,
        message: str,
        priority: int = 0,
        pin: str = "",
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Pass a notification to the queue.

        This is the main entry point used by telegram_handler and other components.

        Args:
            message: Notification message text
            priority: Priority level (higher = more urgent)
            pin: Grouping key (e.g., chat_id)
            metadata: Additional metadata
        """
        notification = Notification(
            message=message,
            priority=priority,
            pin=pin,
        )
        if metadata:
            notification.metadata = metadata
        self.add_notification(notification)
        logger.info(f"Passed notification to queue: pin={pin}, priority={priority}")

    async def get(self) -> Notification | None:
        """Get the next notification from the queue (blocking)."""
        if not self._running:
            return None
        try:
            _, notification = await self._queue.get()
            # Call handlers
            for handler in self._handlers:
                try:
                    result = handler(notification)
                    if asyncio.iscoroutine(result):
                        await result
                except (ValueError, KeyError, TypeError, RuntimeError) as e:
                    logger.error(f"Error in notification handler: {e}")
            return notification
        except asyncio.CancelledError:
            return None
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Error getting notification: {e}")
            return None

    def qsize(self) -> int:
        """Return the current queue size."""
        return self._queue.qsize()


# Singleton instance
_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    """Get global notification manager instance."""
    global _manager
    if _manager is None:
        _manager = NotificationManager()
    return _manager
