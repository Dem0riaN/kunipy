"""Delivery tracking domain models (ТЗ-001 punkt 12-18)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DeliveryState(Enum):
    """Message delivery state (ТЗ-001 punkt 14)."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY_PENDING = "retry_pending"


@dataclass
class MessageDeliveryRecord:
    """Message delivery record (ТЗ-001 punkt 15).

    Tracks message from send to delivery confirmation.
    Implements 10-second verification rule (ТЗ-001 punkt 13).
    """
    message_id: int
    chat_id: int
    state: DeliveryState
    sent_at: datetime

    # Delivery tracking
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    retry_count: int = 0
    error_message: str | None = None

    # Metadata
    text_hash: str | None = None  # For duplicate detection (punkt 18)
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

    def is_within_timeout(self, timeout_seconds: float = 10.0) -> bool:
        """Check if delivery is within timeout (punkt 13)."""
        if not self.delivered_at:
            return False
        return self.delivery_time_seconds() <= timeout_seconds
