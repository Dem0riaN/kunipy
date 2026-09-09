"""Message delivery tracker implementation (ТЗ-001 punkt 12-18)."""

import asyncio
import logging
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from src.interfaces.delivery import IMessageDeliveryTracker, DeliveryState
from src.domain.delivery.models import MessageDeliveryRecord
from src.infrastructure.delivery.storage import MessageDeliveryStorage
from src.infrastructure.delivery.telegram_checker import TelegramMessageDeliveryChecker


logger = logging.getLogger(__name__)


class MessageDeliveryTracker:
    """Tracks and verifies Telegram message delivery.

    Implements ТЗ-001 punkt 12-18:
    - Punkt 12: Storage with all required fields
    - Punkt 13: Separate verification service
    - Punkt 14: 10-second timeout rule
    - Punkt 15: Character-driven retry decision
    - Punkt 16-17: Duplicate prevention
    - Punkt 18: Idempotency
    """

    def __init__(
        self,
        storage: MessageDeliveryStorage,
        checker: TelegramMessageDeliveryChecker
    ):
        """Initialize tracker.

        Args:
            storage: Persistent storage for records
            checker: Telegram delivery verification service
        """
        self._storage = storage
        self._checker = checker
        self._verification_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start background verification loop."""
        if self._running:
            return

        self._running = True
        self._verification_task = asyncio.create_task(self._verification_loop())
        logger.info("Message delivery tracker started")

    async def stop(self) -> None:
        """Stop background verification."""
        if not self._running:
            return

        self._running = False
        if self._verification_task:
            self._verification_task.cancel()
            try:
                await self._verification_task
            except asyncio.CancelledError:
                pass

        logger.info("Message delivery tracker stopped")

    async def track_message(
        self,
        chat_id: int,
        message_id: int,
        text_hash: Optional[str] = None
    ) -> MessageDeliveryRecord:
        """Start tracking message delivery.

        Creates record and begins verification.

        Args:
            chat_id: Target chat ID
            message_id: Sent message ID
            text_hash: Hash for duplicate detection

        Returns:
            Delivery record
        """
        record = MessageDeliveryRecord(
            message_id=message_id,
            chat_id=chat_id,
            state=DeliveryState.SENT,
            sent_at=datetime.now(),
            text_hash=text_hash
        )

        await self._storage.save_record(record)

        logger.debug(
            f"Started tracking message {message_id} in chat {chat_id}"
        )

        return record

    async def check_delivery(
        self,
        record: MessageDeliveryRecord
    ) -> DeliveryState:
        """Check current delivery state.

        Implements ТЗ-001 punkt 13: verification through separate service.

        Args:
            record: Delivery record to check

        Returns:
            Updated delivery state
        """
        # Use checker to verify delivery
        new_state = await self._checker.check_delivery(record)

        # Update record if state changed
        if new_state != record.state:
            record.state = new_state

            if new_state == DeliveryState.DELIVERED:
                record.delivered_at = datetime.now()
            elif new_state == DeliveryState.RETRY_PENDING:
                # Don't increment retry_count yet - that happens on actual retry
                pass

            await self._storage.save_record(record)

            logger.info(
                f"Message {record.message_id} in chat {record.chat_id} "
                f"state: {new_state.value}"
            )

        return new_state

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
        record = await self._storage.get_record(chat_id, message_id)
        if not record:
            return False

        record.state = DeliveryState.DELIVERED
        record.delivered_at = datetime.now()

        await self._storage.save_record(record)

        logger.info(
            f"Marked message {message_id} in chat {chat_id} as delivered"
        )

        return True

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
        record = await self._storage.get_record(chat_id, message_id)
        if not record:
            return False

        record.state = DeliveryState.FAILED
        record.failed_at = datetime.now()
        record.error_message = error

        await self._storage.save_record(record)

        logger.warning(
            f"Marked message {message_id} in chat {chat_id} as failed: {error}"
        )

        return True

    async def should_retry(
        self,
        record: MessageDeliveryRecord
    ) -> bool:
        """Check if message should be retried.

        Implements ТЗ-001 punkt 17: character-driven retry decision support.

        Args:
            record: Delivery record

        Returns:
            True if should retry
        """
        return self._checker.should_retry(record)

    async def get_pending_verifications(self) -> List[MessageDeliveryRecord]:
        """Get all messages pending verification.

        Returns:
            List of records in SENT state
        """
        return await self._storage.get_pending_verifications()

    async def is_duplicate(
        self,
        chat_id: int,
        text_hash: str,
        window_seconds: float = 60.0
    ) -> bool:
        """Check if message is duplicate.

        Implements ТЗ-001 punkt 16-18: prevent duplicate sends.

        Args:
            chat_id: Chat ID
            text_hash: Message text hash
            window_seconds: Duplicate detection window

        Returns:
            True if duplicate detected
        """
        recent = await self._storage.find_recent_by_hash(
            chat_id=chat_id,
            text_hash=text_hash,
            window_seconds=window_seconds
        )

        # Check for any successful or pending deliveries
        for record in recent:
            if record.state in (
                DeliveryState.SENT,
                DeliveryState.DELIVERED,
                DeliveryState.RETRY_PENDING
            ):
                logger.info(
                    f"Duplicate detected in chat {chat_id}: "
                    f"hash {text_hash[:8]}... (existing msg {record.message_id})"
                )
                return True

        return False

    async def _verification_loop(self) -> None:
        """Background loop for checking pending deliveries.

        Runs continuously, checking all SENT messages.
        """
        while self._running:
            try:
                # Get all pending verifications
                pending = await self._storage.get_pending_verifications()

                if pending:
                    logger.debug(f"Checking {len(pending)} pending deliveries")

                    # Check each record
                    for record in pending:
                        try:
                            await self.check_delivery(record)
                        except Exception as e:
                            logger.error(
                                f"Error checking delivery for msg {record.message_id}: {e}",
                                exc_info=True
                            )

                # Sleep between checks
                await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in verification loop: {e}", exc_info=True)
                await asyncio.sleep(5.0)
