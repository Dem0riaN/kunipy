"""Stub notification manager implementation.

Temporary stub until Phase 2 full implementation based on C++ NotificationManager.
"""

from asyncio import Future
from typing import Any

from ...interfaces.worker import Notification, NotificationHandle


class StubNotificationManager:
    """Stub notification manager.

    Minimal implementation for Phase 1.
    Full implementation in Phase 2 based on C++ NotificationManager with worker pins.
    """

    def __init__(self):
        self._queue: list[NotificationHandle] = []

    async def pass_notification(
        self,
        message: str,
        priority: int = 0,
        pin: str | None = None,
        actions: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> NotificationHandle:
        """Pass notification to worker queue.

        Stub: creates handle but doesn't route to workers yet.
        Full worker routing in Phase 2.
        """
        notification = Notification(
            message=message,
            priority=priority,
            pin=pin,
            actions=actions,
            metadata=metadata
        )

        handle = NotificationHandle(
            notification=notification,
            on_started_processing=Future(),
            on_processed=Future()
        )

        self._queue.append(handle)

        # Immediately mark as processed (stub behavior)
        handle.on_started_processing.set_result(None)
        handle.on_processed.set_result(None)

        return handle

    async def remove_notifications(self, substring: str) -> int:
        """Remove notifications matching substring."""
        original_count = len(self._queue)
        self._queue = [
            handle for handle in self._queue
            if substring not in handle.notification.message
        ]
        return original_count - len(self._queue)

    async def get_queue_size(self) -> int:
        """Get current notification queue size."""
        return len(self._queue)

    async def get_worker_count(self) -> int:
        """Get active worker count.

        Stub: returns 0.
        """
        return 0
