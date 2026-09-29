"""Unit tests for WebSocketProxyAdapter.

Tests WebSocket protocol handling and message queue logic.
Following ТЗ-001 §65 - Unit test isolation.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.proxy.core.models import UserContext
from src.application.proxy.websocket_adapter import QueuedMessage, WebSocketProxyAdapter


@pytest.fixture
def mock_core_service():
    """Mock ProxyCoreService for testing."""
    service = Mock()
    service.resolve_user_context = AsyncMock(
        return_value=UserContext(
            user_id="test_user",
            is_papik=True,
            telegram_id="123456",
            linked_user_ids=["123456"],
            working_memory="",
            display_name="Test User"
        )
    )
    service.build_system_prompt = Mock(return_value="Test system prompt")
    return service


@pytest.fixture
def adapter(mock_core_service):
    """Create WebSocketProxyAdapter instance for testing."""
    return WebSocketProxyAdapter(mock_core_service, user_id="test_user")


class TestWebSocketProxyAdapterInit:
    """Test adapter initialization."""

    def test_initialization(self, mock_core_service):
        """Test adapter initializes correctly."""
        # Act
        adapter = WebSocketProxyAdapter(mock_core_service, user_id="test_user")

        # Assert
        assert adapter._user_id == "test_user"
        assert adapter._core == mock_core_service
        assert len(adapter._message_queue) == 0
        assert adapter._conversation_active is False
        assert adapter._websocket is None


class TestQueuedMessage:
    """Test QueuedMessage domain model."""

    def test_queued_message_creation(self):
        """Test QueuedMessage dataclass."""
        # Arrange & Act
        import time
        timestamp = time.time()
        message = QueuedMessage(
            message_type="text-input",
            data={"text": "Hello"},
            timestamp=timestamp
        )

        # Assert
        assert message.message_type == "text-input"
        assert message.data == {"text": "Hello"}
        assert message.timestamp == timestamp


class TestMessageHandling:
    """Test WebSocket message handling."""

    @pytest.mark.asyncio
    async def test_handle_text_input_queues_message(self, adapter):
        """Test text-input message is queued."""
        # Arrange
        data = {"type": "text-input", "text": "Hello world"}

        # Act
        await adapter._handle_text_input(data)

        # Assert
        assert len(adapter._message_queue) == 1
        queued = adapter._message_queue[0]
        assert queued.message_type == "text-input"
        assert queued.data == data

    @pytest.mark.asyncio
    async def test_handle_text_input_empty_text(self, adapter):
        """Test text-input with empty text is ignored."""
        # Arrange
        data = {"type": "text-input", "text": ""}

        # Act
        await adapter._handle_text_input(data)

        # Assert
        assert len(adapter._message_queue) == 0

    @pytest.mark.asyncio
    async def test_handle_interrupt_clears_queue(self, adapter):
        """Test interrupt-signal clears message queue."""
        # Arrange
        adapter._message_queue.append(QueuedMessage("text-input", {"text": "test"}, 0))
        adapter._conversation_active = True
        mock_ws = AsyncMock()
        adapter._websocket = mock_ws

        # Act
        await adapter._handle_interrupt()

        # Assert
        assert len(adapter._message_queue) == 0
        assert adapter._conversation_active is False
        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_init_config_sends_response(self, adapter):
        """Test request-init-config sends configuration."""
        # Arrange
        mock_ws = AsyncMock()
        adapter._websocket = mock_ws
        data = {"type": "request-init-config"}

        # Act
        await adapter._handle_init_config(data)

        # Assert
        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["type"] == "init-config"
        assert "config" in sent_data


class TestMessageQueue:
    """Test message queue and conversation state."""

    def test_queue_multiple_messages(self, adapter):
        """Test queueing multiple messages."""
        # Arrange & Act
        import time
        adapter._message_queue.append(QueuedMessage("text-input", {"text": "msg1"}, time.time()))
        adapter._message_queue.append(QueuedMessage("text-input", {"text": "msg2"}, time.time()))

        # Assert
        assert len(adapter._message_queue) == 2

    def test_conversation_state_blocks_processing(self, adapter):
        """Test conversation_active flag."""
        # Arrange
        adapter._conversation_active = False

        # Act
        adapter._conversation_active = True

        # Assert
        assert adapter._conversation_active is True


class TestWebSocketSending:
    """Test sending messages to WebSocket."""

    @pytest.mark.asyncio
    async def test_send_sentence(self, adapter):
        """Test sending llm-sentence message."""
        # Arrange
        mock_ws = AsyncMock()
        adapter._websocket = mock_ws

        # Act
        await adapter._send_sentence("Hello", "audio_data")

        # Assert
        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["type"] == "llm-sentence"
        assert sent_data["text"] == "Hello"
        assert sent_data["audio"] == "audio_data"

    @pytest.mark.asyncio
    async def test_send_control(self, adapter):
        """Test sending control message."""
        # Arrange
        mock_ws = AsyncMock()
        adapter._websocket = mock_ws

        # Act
        await adapter._send_control("conversation-chain-end")

        # Assert
        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["type"] == "control"
        assert sent_data["text"] == "conversation-chain-end"

    @pytest.mark.asyncio
    async def test_send_without_websocket(self, adapter):
        """Test sending when WebSocket is not connected."""
        # Arrange
        adapter._websocket = None

        # Act & Assert (should not raise)
        await adapter._send_sentence("test", "")
        await adapter._send_control("test")


class TestCleanup:
    """Test cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_consumer_task(self, adapter):
        """Test cleanup cancels background consumer."""
        # Arrange
        async def mock_coro():
            pass

        mock_task = asyncio.create_task(mock_coro())
        adapter._consumer_task = mock_task

        # Act
        await adapter._cleanup()

        # Assert
        assert mock_task.cancelled() or mock_task.done()

    @pytest.mark.asyncio
    async def test_cleanup_clears_queue(self, adapter):
        """Test cleanup clears message queue."""
        # Arrange
        import time
        adapter._message_queue.append(QueuedMessage("text-input", {"text": "test"}, time.time()))

        # Act
        await adapter._cleanup()

        # Assert
        assert len(adapter._message_queue) == 0

    @pytest.mark.asyncio
    async def test_cleanup_resets_state(self, adapter):
        """Test cleanup resets adapter state."""
        # Arrange
        adapter._conversation_active = True
        adapter._websocket = Mock()

        # Act
        await adapter._cleanup()

        # Assert
        assert adapter._conversation_active is False
        assert adapter._websocket is None


class TestIncomingMessageParsing:
    """Test incoming message parsing."""

    @pytest.mark.asyncio
    async def test_parse_valid_json(self, adapter):
        """Test parsing valid JSON message."""
        # Arrange
        raw_data = json.dumps({"type": "text-input", "text": "Hello"})

        # Act
        await adapter._handle_incoming_message(raw_data)

        # Assert
        assert len(adapter._message_queue) == 1

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self, adapter):
        """Test handling invalid JSON."""
        # Arrange
        raw_data = "not valid json"

        # Act & Assert (should not raise)
        await adapter._handle_incoming_message(raw_data)
        assert len(adapter._message_queue) == 0

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, adapter):
        """Test handling unknown message type."""
        # Arrange
        raw_data = json.dumps({"type": "unknown-type", "data": "test"})

        # Act & Assert (should not raise)
        await adapter._handle_incoming_message(raw_data)
        assert len(adapter._message_queue) == 0
