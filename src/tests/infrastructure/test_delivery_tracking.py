"""Tests for message delivery tracking (ТЗ-001 punkt 66)."""

import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from src.infrastructure.delivery.storage import MessageDeliveryStorage
from src.infrastructure.delivery.tracker import MessageDeliveryTracker
from src.infrastructure.delivery.telegram_checker import TelegramMessageDeliveryChecker
from src.interfaces.delivery import DeliveryState
from src.domain.delivery.models import MessageDeliveryRecord
from src.domain.models import TelegramMessage


class MockTelegramClient:
    """Mock Telegram client for testing."""

    def __init__(self):
        self.delivered_messages = set()  # (chat_id, message_id)
        self.chat_histories = {}  # chat_id -> list[TelegramMessage]

    async def get_chat_history(
        self,
        chat_id: int,
        from_message_id: int,
        limit: int
    ) -> List[TelegramMessage]:
        """Mock chat history retrieval."""
        history = self.chat_histories.get(chat_id, [])

        # Filter messages around from_message_id
        relevant = [
            msg for msg in history
            if msg.message_id <= from_message_id
        ]

        return relevant[:limit]

    def mark_delivered(self, chat_id: int, message_id: int) -> None:
        """Mark message as delivered in mock."""
        self.delivered_messages.add((chat_id, message_id))

        # Add to chat history
        if chat_id not in self.chat_histories:
            self.chat_histories[chat_id] = []

        msg = TelegramMessage(
            message_id=message_id,
            chat_id=chat_id,
            user_id=0,  # Bot's message
            text="Test message",
            timestamp=datetime.now()
        )
        self.chat_histories[chat_id].append(msg)


@pytest.fixture
async def storage(tmp_path: Path):
    """Create temporary storage."""
    db_path = tmp_path / "delivery_test.db"
    storage = MessageDeliveryStorage(db_path)
    await storage.initialize()
    yield storage
    await storage.close()


@pytest.fixture
def mock_client():
    """Create mock Telegram client."""
    return MockTelegramClient()


@pytest.fixture
async def tracker(storage, mock_client):
    """Create tracker with mocks."""
    checker = TelegramMessageDeliveryChecker(mock_client)
    tracker = MessageDeliveryTracker(storage, checker)
    await tracker.start()
    yield tracker
    await tracker.stop()


class TestDeliveryTracking:
    """Test suite for delivery tracking (ТЗ-001 punkt 66)."""

    @pytest.mark.asyncio
    async def test_successful_delivery(self, tracker, mock_client):
        """Test 1: Успешная доставка сообщения.

        ТЗ-001 punkt 66.1: Verify successful delivery path.
        """
        chat_id = 123
        message_id = 456
        text_hash = MessageDeliveryStorage.compute_text_hash("Test message")

        # Track message
        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id,
            text_hash=text_hash
        )

        assert record.state == DeliveryState.SENT
        assert record.message_id == message_id
        assert record.chat_id == chat_id

        # Simulate delivery
        mock_client.mark_delivered(chat_id, message_id)

        # Check delivery
        await asyncio.sleep(0.1)  # Let verification loop run
        new_state = await tracker.check_delivery(record)

        assert new_state == DeliveryState.DELIVERED
        assert record.delivered_at is not None
        assert record.delivery_time_seconds() is not None
        assert record.delivery_time_seconds() < 1.0

    @pytest.mark.asyncio
    async def test_delivery_not_confirmed_under_10_seconds(
        self,
        tracker,
        mock_client
    ):
        """Test 2: Недоставка < 10 секунд.

        ТЗ-001 punkt 66.2: Message not delivered but within timeout.
        """
        chat_id = 123
        message_id = 457
        text_hash = MessageDeliveryStorage.compute_text_hash("Test message 2")

        # Track message
        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id,
            text_hash=text_hash
        )

        # Don't simulate delivery - message not in history
        # Check within 10 seconds
        await asyncio.sleep(0.1)
        new_state = await tracker.check_delivery(record)

        # Should still be SENT (waiting)
        assert new_state == DeliveryState.SENT
        assert record.delivered_at is None

    @pytest.mark.asyncio
    async def test_delivery_timeout_triggers_retry(
        self,
        tracker,
        storage,
        mock_client
    ):
        """Test 3: Недоставка >= 10 секунд → retry_pending.

        ТЗ-001 punkt 66.3: Timeout triggers retry eligibility.
        """
        chat_id = 123
        message_id = 458
        text_hash = MessageDeliveryStorage.compute_text_hash("Test message 3")

        # Track message with backdated send time
        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id,
            text_hash=text_hash
        )

        # Backdate to 11 seconds ago
        record.sent_at = datetime.now() - timedelta(seconds=11)
        await storage.save_record(record)

        # Check delivery - should trigger retry
        new_state = await tracker.check_delivery(record)

        assert new_state == DeliveryState.RETRY_PENDING
        assert record.delivered_at is None

        # Verify retry is allowed
        should_retry = await tracker.should_retry(record)
        assert should_retry is True

    @pytest.mark.asyncio
    async def test_duplicate_prevention(self, tracker, storage):
        """Test 4: Предотвращение дубликатов.

        ТЗ-001 punkt 66.4: Duplicate detection within time window.
        """
        chat_id = 123
        text = "Duplicate test message"
        text_hash = MessageDeliveryStorage.compute_text_hash(text)

        # Send first message
        record1 = await tracker.track_message(
            chat_id=chat_id,
            message_id=460,
            text_hash=text_hash
        )

        # Try to send duplicate within 60 seconds
        is_duplicate = await tracker.is_duplicate(
            chat_id=chat_id,
            text_hash=text_hash,
            window_seconds=60.0
        )

        assert is_duplicate is True

        # Wait and check outside window
        # (For testing, we'll modify the record timestamp)
        record1.sent_at = datetime.now() - timedelta(seconds=61)
        await storage.save_record(record1)

        is_duplicate = await tracker.is_duplicate(
            chat_id=chat_id,
            text_hash=text_hash,
            window_seconds=60.0
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_duplicate_different_chats(self, tracker):
        """Test 4b: Same text in different chats is not duplicate.

        ТЗ-001 punkt 18: Duplicate detection is per-chat.
        """
        text = "Same message"
        text_hash = MessageDeliveryStorage.compute_text_hash(text)

        # Send to chat 1
        await tracker.track_message(
            chat_id=100,
            message_id=500,
            text_hash=text_hash
        )

        # Send to chat 2 - should NOT be duplicate
        is_duplicate = await tracker.is_duplicate(
            chat_id=200,
            text_hash=text_hash,
            window_seconds=60.0
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_storage_survives_restart(self, tmp_path):
        """Test 5: Хранилище переживает рестарт.

        ТЗ-001 punkt 66.5: Records persist across process restarts.
        """
        db_path = tmp_path / "restart_test.db"

        # First session
        storage1 = MessageDeliveryStorage(db_path)
        await storage1.initialize()

        record = MessageDeliveryRecord(
            message_id=600,
            chat_id=300,
            state=DeliveryState.SENT,
            sent_at=datetime.now(),
            text_hash="abc123"
        )
        await storage1.save_record(record)
        await storage1.close()

        # Simulate restart - new storage instance
        storage2 = MessageDeliveryStorage(db_path)
        await storage2.initialize()

        # Retrieve record
        retrieved = await storage2.get_record(
            chat_id=300,
            message_id=600
        )

        assert retrieved is not None
        assert retrieved.message_id == 600
        assert retrieved.chat_id == 300
        assert retrieved.state == DeliveryState.SENT
        assert retrieved.text_hash == "abc123"

        await storage2.close()

    @pytest.mark.asyncio
    async def test_concurrent_verification_no_race(
        self,
        tracker,
        storage,
        mock_client
    ):
        """Test 6: Race conditions handled correctly.

        ТЗ-001 punkt 66.6: Concurrent checks don't corrupt state.
        """
        chat_id = 400
        message_id = 700
        text_hash = MessageDeliveryStorage.compute_text_hash("Race test")

        # Track message
        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id,
            text_hash=text_hash
        )

        # Simulate delivery
        mock_client.mark_delivered(chat_id, message_id)

        # Run multiple concurrent checks
        results = await asyncio.gather(
            tracker.check_delivery(record),
            tracker.check_delivery(record),
            tracker.check_delivery(record),
            tracker.check_delivery(record)
        )

        # All should return DELIVERED
        assert all(state == DeliveryState.DELIVERED for state in results)

        # Retrieve from storage - should be consistent
        final_record = await storage.get_record(chat_id, message_id)
        assert final_record is not None
        assert final_record.state == DeliveryState.DELIVERED
        assert final_record.delivered_at is not None

    @pytest.mark.asyncio
    async def test_max_retry_limit(self, tracker, storage):
        """Test retry limit enforcement.

        ТЗ-001 punkt 17: Retry attempts are limited.
        """
        chat_id = 500
        message_id = 800
        text_hash = MessageDeliveryStorage.compute_text_hash("Retry test")

        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id,
            text_hash=text_hash
        )

        # Mark for retry
        record.state = DeliveryState.RETRY_PENDING

        # Try 3 retries
        for i in range(3):
            assert await tracker.should_retry(record) is True
            record.retry_count += 1
            await storage.save_record(record)

        # Fourth retry should be rejected
        assert await tracker.should_retry(record) is False

    @pytest.mark.asyncio
    async def test_mark_failed_with_error(self, tracker, storage):
        """Test marking message as failed.

        Verify error messages are stored correctly.
        """
        chat_id = 600
        message_id = 900

        record = await tracker.track_message(
            chat_id=chat_id,
            message_id=message_id
        )

        # Mark as failed
        error_msg = "Network timeout"
        success = await tracker.mark_failed(
            chat_id=chat_id,
            message_id=message_id,
            error=error_msg
        )

        assert success is True

        # Retrieve and verify
        retrieved = await storage.get_record(chat_id, message_id)
        assert retrieved is not None
        assert retrieved.state == DeliveryState.FAILED
        assert retrieved.error_message == error_msg
        assert retrieved.failed_at is not None

    @pytest.mark.asyncio
    async def test_cleanup_old_records(self, storage):
        """Test cleanup of old delivered/failed records.

        Verify storage doesn't grow unbounded.
        """
        # Create old delivered record
        old_record = MessageDeliveryRecord(
            message_id=1000,
            chat_id=700,
            state=DeliveryState.DELIVERED,
            sent_at=datetime.now() - timedelta(days=8),
            delivered_at=datetime.now() - timedelta(days=8)
        )
        await storage.save_record(old_record)

        # Create recent record
        recent_record = MessageDeliveryRecord(
            message_id=1001,
            chat_id=700,
            state=DeliveryState.DELIVERED,
            sent_at=datetime.now() - timedelta(days=1),
            delivered_at=datetime.now() - timedelta(days=1)
        )
        await storage.save_record(recent_record)

        # Cleanup records older than 7 days
        deleted = await storage.cleanup_old_records(days=7)
        assert deleted == 1

        # Verify old record gone, recent remains
        old_retrieved = await storage.get_record(700, 1000)
        assert old_retrieved is None

        recent_retrieved = await storage.get_record(700, 1001)
        assert recent_retrieved is not None

    @pytest.mark.asyncio
    async def test_pending_verifications_query(self, storage):
        """Test querying pending verifications.

        Verify tracker can find all SENT messages.
        """
        # Create mixed state records
        await storage.save_record(MessageDeliveryRecord(
            message_id=1100,
            chat_id=800,
            state=DeliveryState.SENT,
            sent_at=datetime.now()
        ))

        await storage.save_record(MessageDeliveryRecord(
            message_id=1101,
            chat_id=800,
            state=DeliveryState.DELIVERED,
            sent_at=datetime.now(),
            delivered_at=datetime.now()
        ))

        await storage.save_record(MessageDeliveryRecord(
            message_id=1102,
            chat_id=800,
            state=DeliveryState.SENT,
            sent_at=datetime.now()
        ))

        # Query pending
        pending = await storage.get_pending_verifications()

        assert len(pending) == 2
        assert all(r.state == DeliveryState.SENT for r in pending)
        assert {r.message_id for r in pending} == {1100, 1102}
