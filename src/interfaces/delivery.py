"""Message delivery tracking protocols (ТЗ-001 punkt 12-18)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class DeliveryState(Enum):
    """Message delivery state (ТЗ-001 punkt 14).

    State machine:
    PENDING → SENT → DELIVERED
    PENDING → SENT → RETRY_PENDING → SENT → DELIVERED
    PENDING → SENT → FAILED
    """
    PENDING = "pending"      # Message created, not yet sent
    SENT = "sent"           # Sent to Telegram, awaiting confirmation
    DELIVERED = "delivered"  # Confirmed delivered within 10 seconds
    FAILED = "failed"       # Delivery failed permanently
    RETRY_PENDING = "retry_pending"  # Waiting to retry after timeout


@dataclass
class MessageDeliveryRecord:
    """Message delivery record (ТЗ-001 punkt 15).

    Tracks message from send to delivery confirmation.
    """
    message_id: int
    chat_id: int
    state: DeliveryState
    sent_at: datetime
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    retry_count: int = 0
    error_message: str | None = None

    # Metadata
    text_hash: str | None = None  # For duplicate detection
    worker_id: int | None = None  # Which worker sent it

    def is_delivered(self) -> bool:
        """Check if message was delivered."""
        return self.state == DeliveryState.DELIVERED

    def is_pending_retry(self) -> bool:
        """Check if message needs retry."""
        return self.state == DeliveryState.RETRY_PENDING

    def delivery_time_seconds(self) -> float | None:
        """Calculate delivery time in seconds."""
        if self.delivered_at and self.sent_at:
            return (self.delivered_at - self.sent_at).total_seconds()
        return None


class IMessageDeliveryTracker(Protocol):
    """Protocol for message delivery tracking.

    Implements ТЗ-001 punkt 12-18 delivery verification.
    Implementation deferred to Phase 2.
    """

    async def track_message(
        self,
        chat_id: int,
        message_id: int,
        text_hash: str | None = None
    ) -> MessageDeliveryRecord:
        """Start tracking message delivery.

        Creates PENDING record and begins verification.

        Args:
            chat_id: Target chat ID
            message_id: Sent message ID
            text_hash: Hash for duplicate detection

        Returns:
            Delivery record
        """
        ...

    async def check_delivery(
        self,
        record: MessageDeliveryRecord
    ) -> DeliveryState:
        """Check current delivery state.

        Implements ТЗ-001 punkt 13: 10-second verification rule.

        Args:
            record: Delivery record to check

        Returns:
            Updated delivery state
        """
        ...

    async def mark_delivered(
        self,
        chat_id: int,
        message_id: int
    ) -> bool:
        """Mark message as delivered.

        Args:
            chat_id: Chat ID
            message_id: Message ID

        Returns:
            True if updated
        """
        ...

    async def mark_failed(
        self,
        chat_id: int,
        message_id: int,
        error: str
    ) -> bool:
        """Mark message as failed.

        Args:
            chat_id: Chat ID
            message_id: Message ID
            error: Error description

        Returns:
            True if updated
        """
        ...

    async def should_retry(
        self,
        record: MessageDeliveryRecord
    ) -> bool:
        """Check if message should be retried.

        Implements ТЗ-001 punkt 17: timeout triggers retry.

        Args:
            record: Delivery record

        Returns:
            True if should retry
        """
        ...

    async def get_pending_verifications(self) -> list[MessageDeliveryRecord]:
        """Get all messages pending verification.

        Returns:
            List of records in SENT state
        """
        ...

    async def is_duplicate(
        self,
        chat_id: int,
        text_hash: str,
        window_seconds: float = 60.0
    ) -> bool:
        """Check if message is duplicate.

        Implements ТЗ-001 punkt 18: prevent duplicate sends.

        Args:
            chat_id: Chat ID
            text_hash: Message text hash
            window_seconds: Duplicate detection window

        Returns:
            True if duplicate detected
        """
        ...
