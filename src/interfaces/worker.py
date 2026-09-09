"""Worker and notification protocols.

Based on C++ NotificationManager architecture (kuni-cpp/src/NotificationManager.h).
"""

from typing import Protocol, Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass
from asyncio import Future


@dataclass
class Notification:
    """Notification passed to worker queue.

    Based on C++ NotificationManager::Notification.
    """
    message: str  # Natural language notification for LLM
    priority: int = 0  # Higher priority processed first
    pin: Optional[str] = None  # Worker affinity (e.g., "<chat id=123 />")
    actions: Optional[Dict[str, Any]] = None  # Available tools for this notification
    metadata: Dict[str, Any] = None  # Additional context

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class NotificationHandle:
    """Handle for tracking notification processing.

    Based on C++ NotificationManager::NotificationHandle.
    """
    notification: Notification
    on_started_processing: Future  # Resolves when worker picks up notification
    on_processed: Future  # Resolves when worker finishes processing


class INotificationManager(Protocol):
    """Protocol for notification management.

    Based on C++ NotificationManager with worker pins and priority queue.
    Implements worker affinity: notifications with matching pins route to the same worker.
    """

    async def pass_notification(
        self,
        message: str,
        priority: int = 0,
        pin: Optional[str] = None,
        actions: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NotificationHandle:
        """Pass notification to worker queue.

        Notifications are routed to workers based on:
        1. Pin affinity (same chat → same worker)
        2. Priority (higher first)
        3. FIFO within same priority

        Args:
            message: Natural language notification for LLM
            priority: Processing priority (higher = earlier)
            pin: Worker affinity token (e.g., chat ID)
            actions: Available tools for this notification
            metadata: Additional context

        Returns:
            Handle for tracking processing
        """
        ...

    async def remove_notifications(self, substring: str) -> int:
        """Remove notifications matching substring.

        Used to remove obsolete notifications from queue.
        Example: Remove "New message from User X" when user is now offline.

        Args:
            substring: String to match in notification messages

        Returns:
            Number of notifications removed
        """
        ...

    async def get_queue_size(self) -> int:
        """Get current notification queue size.

        Returns:
            Number of pending notifications
        """
        ...

    async def get_worker_count(self) -> int:
        """Get active worker count.

        Returns:
            Number of registered workers
        """
        ...


class IWorkerOrchestrator(Protocol):
    """Protocol for worker pool management."""

    async def start_workers(self, count: int) -> None:
        """Start worker pool.

        Args:
            count: Number of workers to start
        """
        ...

    async def stop_workers(self) -> None:
        """Stop all workers gracefully."""
        ...

    async def get_worker_stats(self) -> Dict[str, Any]:
        """Get worker statistics.

        Returns:
            Worker stats (processed count, pins, etc.)
        """
        ...
