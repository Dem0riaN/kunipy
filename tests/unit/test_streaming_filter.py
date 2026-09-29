"""Unit tests for StreamingFilter."""

import pytest

from src.application.proxy.session_manager import SessionManager
from src.application.proxy.streaming_filter import (
    StreamingFilter,
    StreamState,
    ToolCallAccumulator,
)


@pytest.fixture
def session_manager():
    """Create session manager for testing."""
    return SessionManager(session_timeout_minutes=30)


@pytest.fixture
def streaming_filter(session_manager):
    """Create streaming filter for testing."""
    return StreamingFilter(session_manager)


class TestToolCallAccumulator:
    """Test tool call accumulation logic."""

    def test_accumulator_initialization(self):
        """Test accumulator starts empty."""
        acc = ToolCallAccumulator()

        assert acc.id == ""
        assert acc.type == ""
        assert acc.function_name == ""
        assert acc.function_args == ""
        assert acc.chunks == []

    def test_accumulate_single_chunk(self):
        """Test accumulating single tool call chunk."""
        acc = ToolCallAccumulator()

        chunk = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query":'
                        }
                    }]
                }
            }]
        }

        acc.add_chunk(chunk)

        assert acc.id == "call_123"
        assert acc.type == "function"
        assert acc.function_name == "web_search"
        assert acc.function_args == '{"query":'
        assert len(acc.chunks) == 1

    def test_accumulate_multiple_chunks(self):
        """Test accumulating multiple chunks for one tool call."""
        acc = ToolCallAccumulator()

        # First chunk - id and name
        chunk1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "id": "call_456",
                        "type": "function",
                        "function": {
                            "name": "ask",
                            "arguments": '{"question":'
                        }
                    }]
                }
            }]
        }

        # Second chunk - more arguments
        chunk2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "function": {
                            "arguments": ' "test"}'
                        }
                    }]
                }
            }]
        }

        acc.add_chunk(chunk1)
        acc.add_chunk(chunk2)

        assert acc.id == "call_456"
        assert acc.function_name == "ask"
        assert acc.function_args == '{"question": "test"}'
        assert len(acc.chunks) == 2

    def test_is_complete_with_finish_reason(self):
        """Test detecting tool call completion."""
        acc = ToolCallAccumulator()

        # Incomplete chunk
        chunk1 = {
            "choices": [{
                "delta": {"tool_calls": [{"id": "call_1"}]},
                "finish_reason": None
            }]
        }
        assert not acc.is_complete(chunk1)

        # Complete chunk
        chunk2 = {
            "choices": [{
                "delta": {},
                "finish_reason": "tool_calls"
            }]
        }
        assert acc.is_complete(chunk2)

    def test_to_message_format(self):
        """Test converting accumulator to message format."""
        acc = ToolCallAccumulator()
        acc.id = "call_789"
        acc.type = "function"
        acc.function_name = "web_search"
        acc.function_args = '{"query": "test"}'

        message = acc.to_message()

        assert message["role"] == "assistant"
        assert message["content"] is None
        assert len(message["tool_calls"]) == 1
        assert message["tool_calls"][0]["id"] == "call_789"
        assert message["tool_calls"][0]["function"]["name"] == "web_search"


class TestStreamingFilter:
    """Test StreamingFilter real-time chunk processing."""

    def test_initialization(self, streaming_filter):
        """Test filter initializes correctly."""
        assert streaming_filter._state == StreamState.CONTENT
        assert streaming_filter._tool_accumulator is None

    @pytest.mark.asyncio
    async def test_pass_through_content_chunk(self, streaming_filter):
        """Test regular content chunks pass through unchanged."""
        chunk = {
            "id": "chatcmpl-123",
            "choices": [{
                "delta": {"content": "Hello"},
                "finish_reason": None
            }]
        }

        filtered, hidden = await streaming_filter.filter_chunk(chunk, "session_1")

        assert filtered == chunk
        assert hidden == []

    @pytest.mark.asyncio
    async def test_filter_tool_call_chunk(self, streaming_filter):
        """Test tool call chunks are filtered from client."""
        chunk = {
            "id": "chatcmpl-456",
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "ask", "arguments": "{}"}
                    }]
                },
                "finish_reason": None
            }]
        }

        filtered, hidden = await streaming_filter.filter_chunk(chunk, "session_2")

        assert filtered is None  # Filtered from client
        assert hidden == []  # Not complete yet

    @pytest.mark.asyncio
    async def test_complete_tool_call_sequence(self, streaming_filter):
        """Test complete tool call sequence returns hidden message."""
        # First chunk - start tool call
        chunk1 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query":'}
                    }]
                }
            }]
        }

        # Second chunk - continue arguments
        chunk2 = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "function": {"arguments": ' "test"}'}
                    }]
                }
            }]
        }

        # Final chunk - finish
        chunk3 = {
            "choices": [{
                "delta": {},
                "finish_reason": "tool_calls"
            }]
        }

        # Process chunks
        filtered1, hidden1 = await streaming_filter.filter_chunk(chunk1, "session_3")
        assert filtered1 is None
        assert hidden1 == []

        filtered2, hidden2 = await streaming_filter.filter_chunk(chunk2, "session_3")
        assert filtered2 is None
        assert hidden2 == []

        filtered3, hidden3 = await streaming_filter.filter_chunk(chunk3, "session_3")
        assert filtered3 is None
        assert len(hidden3) == 1

        # Verify hidden message format
        message = hidden3[0]
        assert message["role"] == "assistant"
        assert message["tool_calls"][0]["id"] == "call_abc"
        assert message["tool_calls"][0]["function"]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_reset_after_tool_call(self, streaming_filter):
        """Test filter resets state after tool call completes."""
        # Complete a tool call
        chunk = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "ask", "arguments": "{}"}
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }

        await streaming_filter.filter_chunk(chunk, "session_4")

        # Verify state reset
        assert streaming_filter._state == StreamState.CONTENT
        assert streaming_filter._tool_accumulator is None

    def test_is_tool_call_chunk_detection(self, streaming_filter):
        """Test tool call chunk detection logic."""
        # Content chunk
        content = {
            "choices": [{
                "delta": {"content": "text"},
                "finish_reason": None
            }]
        }
        assert not streaming_filter._is_tool_call_chunk(content)

        # Tool call chunk with delta
        tool_delta = {
            "choices": [{
                "delta": {"tool_calls": [{"id": "call_1"}]},
                "finish_reason": None
            }]
        }
        assert streaming_filter._is_tool_call_chunk(tool_delta)

        # Tool call chunk with finish_reason
        tool_finish = {
            "choices": [{
                "delta": {},
                "finish_reason": "tool_calls"
            }]
        }
        assert streaming_filter._is_tool_call_chunk(tool_finish)

    def test_reset_method(self, streaming_filter):
        """Test manual reset."""
        streaming_filter._state = StreamState.TOOL_CALL
        streaming_filter._tool_accumulator = ToolCallAccumulator()

        streaming_filter.reset()

        assert streaming_filter._state == StreamState.CONTENT
        assert streaming_filter._tool_accumulator is None
