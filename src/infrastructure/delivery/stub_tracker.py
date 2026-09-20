"""Stub delivery tracker implementation.

Temporary stub until Phase 2 full implementation.
"""

from datetime import UTC, datetime

from ...domain.delivery.models import DeliveryState, MessageDeliveryRecord


class StubDeliveryTracker:
    """Stub delivery tracker.

    Minimal implementation for Phase 1.
    Full implementation in Phase 2 with proper verification.
    """

    def __init__(self):
        self._records: dict[tuple[int, int], MessageDeliveryRecord] = {}

    def _key(self, chat_id: int, message_id: int) -> tuple[int, int]:
        """Create record key."""
        return (chat_id, message_id)

    async def track_message(
        self,
        chat_id: int,
        message_id: int,
        text_hash: str | None = None
    ) -> MessageDeliveryRecord:
        """Start tracking message delivery."""
        record = MessageDeliveryRecord(
            message_id=message_id,
            chat_id=chat_id,
            state=DeliveryState.SENT,
            sent_at=datetime.now(UTC),
            text_hash=text_hash
        )
        key = self._key(chat_id, message_id)
        self._records[key] = record
        return record

    async def check_delivery(
        self,
        record: MessageDeliveryRecord
    ) -> DeliveryState:
        """Check current delivery state.

        Stub: always returns DELIVERED.
        Real implementation in Phase 2 will verify via Telegram API.
        """
        return DeliveryState.DELIVERED

    async def mark_delivered(
        self,
        chat_id: int,
        message_id: int
    ) -> bool:
        """Mark message as delivered."""
        key = self._key(chat_id, message_id)
        if key in self._records:
            record = self._records[key]
            record.state = DeliveryState.DELIVERED
            record.delivered_at = datetime.now(UTC)
            return True
        return False

    async def mark_failed(
        self,
        chat_id: int,
        message_id: int,
        error: str
    ) -> bool:
        """Mark message as failed."""
        key = self._key(chat_id, message_id)
        if key in self._records:
            record = self._records[key]
            record.state = DeliveryState.FAILED
            record.failed_at = datetime.now(UTC)
            record.error_message = error
            return True
        return False

    async def should_retry(
        self,
        record: MessageDeliveryRecord
    ) -> bool:
        """Check if message should be retried."""
        if record.retry_count >= 3:
            return False

        if record.state == DeliveryState.RETRY_PENDING:
            return True

        # Check timeout (10 seconds from ТЗ-001)
        if record.state == DeliveryState.SENT:
            elapsed = (datetime.now(UTC) - record.sent_at).total_seconds()
            return elapsed >= 10.0

        return False

    async def get_pending_verifications(self) -> list[MessageDeliveryRecord]:
        """Get all messages pending verification."""
        return [
            record for record in self._records.values()
            if record.state == DeliveryState.SENT
        ]

    async def is_duplicate(
        self,
        chat_id: int,
        text_hash: str,
        window_seconds: float = 60.0
    ) -> bool:
        """Check if message is duplicate.

        Stub: always returns False.
        Real implementation in Phase 2.
        """
        return False
