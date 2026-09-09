"""Telegram delivery verification service (ТЗ-001 punkt 13)."""

from typing import Optional
from datetime import datetime, timedelta
import logging

from src.interfaces.telegram import ITelegramClient
from src.interfaces.delivery import DeliveryState
from src.domain.delivery.models import MessageDeliveryRecord


logger = logging.getLogger(__name__)


class TelegramMessageDeliveryChecker:
    """Checks message delivery via Telegram API.

    Implements ТЗ-001 punkt 13: verify delivery through separate service.
    Uses chat history to confirm message presence.
    """

    # ТЗ-001 punkt 14: 10-second rule
    DELIVERY_TIMEOUT_SECONDS = 10.0

    def __init__(self, telegram_client: ITelegramClient):
        """Initialize checker.

        Args:
            telegram_client: Low-level Telegram API client
        """
        self._client = telegram_client

    async def check_delivery(
        self,
        record: MessageDeliveryRecord
    ) -> DeliveryState:
        """Check message delivery status.

        Implements ТЗ-001 punkt 13-14: verify delivery and apply 10-second rule.

        Args:
            record: Delivery record to check

        Returns:
            Updated delivery state
        """
        # Already in terminal state
        if record.state in (DeliveryState.DELIVERED, DeliveryState.FAILED):
            return record.state

        # Not yet sent
        if record.state == DeliveryState.PENDING:
            return DeliveryState.PENDING

        # Check if message appears in chat history
        try:
            is_delivered = await self._verify_in_chat_history(
                record.chat_id,
                record.message_id
            )

            if is_delivered:
                return DeliveryState.DELIVERED

        except Exception as e:
            logger.warning(
                f"Delivery check failed for msg {record.message_id} "
                f"in chat {record.chat_id}: {e}"
            )
            # Don't mark as failed yet, might be transient

        # ТЗ-001 punkt 14: Apply 10-second timeout rule
        elapsed = (datetime.now() - record.sent_at).total_seconds()

        if elapsed >= self.DELIVERY_TIMEOUT_SECONDS:
            # Timeout reached, mark for retry
            logger.info(
                f"Message {record.message_id} in chat {record.chat_id} "
                f"not delivered after {elapsed:.1f}s, marking for retry"
            )
            return DeliveryState.RETRY_PENDING

        # Still within timeout window
        return DeliveryState.SENT

    async def _verify_in_chat_history(
        self,
        chat_id: int,
        message_id: int
    ) -> bool:
        """Check if message appears in chat history.

        Args:
            chat_id: Chat ID
            message_id: Message ID to verify

        Returns:
            True if message found in history
        """
        # Strategy: Get recent chat history and check for our message ID
        # TDLib provides getChatHistory which returns messages around a point

        try:
            # Get last 20 messages from chat
            history = await self._client.get_chat_history(
                chat_id=chat_id,
                from_message_id=message_id + 20,  # Start slightly ahead
                limit=20
            )

            # Check if our message is in the history
            message_ids = [msg.message_id for msg in history]
            return message_id in message_ids

        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return False

    def should_retry(self, record: MessageDeliveryRecord) -> bool:
        """Check if message should be retried.

        Implements ТЗ-001 punkt 17: determine retry eligibility.

        Args:
            record: Delivery record

        Returns:
            True if retry is recommended
        """
        # Only retry if in RETRY_PENDING state
        if record.state != DeliveryState.RETRY_PENDING:
            return False

        # Limit retry attempts
        MAX_RETRIES = 3
        if record.retry_count >= MAX_RETRIES:
            logger.warning(
                f"Message {record.message_id} in chat {record.chat_id} "
                f"reached max retries ({MAX_RETRIES})"
            )
            return False

        return True
