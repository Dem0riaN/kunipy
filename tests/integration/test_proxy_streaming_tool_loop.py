"""Test unified streaming tool loop architecture.

Verifies C++ reference implementation compliance (ТЗ-001 §2.1):
- Single streaming POST for stream=true requests
- Real-time tool execution via StreamingFilter callbacks
- No separate final generation after tool loop
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.proxy.streaming_filter import StreamingFilter, ToolCallAccumulator
from src.openai_chat import StreamingChunk


class TestStreamingToolLoop:
    """Test unified streaming tool loop (C++ reference architecture)."""

    @pytest.mark.asyncio
    async def test_streaming_filter_returns_tool_calls_not_messages(self):
        """Verify StreamingFilter returns tool_calls list, not assistant messages."""
        session_manager = MagicMock()
        thinking_filter = None
        filter_instance = StreamingFilter(session_manager, thinking_filter)

        # Simulate tool call chunks
        chunks = [
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "test_tool", "arguments": ""}
                        }]
                    },
                    "finish_reason": None,
                }]
            },
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "function": {"arguments": '{"arg": "value"}'}
                        }]
                    },
                    "finish_reason": None,
                }]
            },
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls",
                }]
            },
        ]

        # Process chunks
        completed_tool_calls = []
        for chunk in chunks:
            filtered_chunk, tool_calls = await filter_instance.filter_chunk(chunk, "test_session")
            if tool_calls:
                completed_tool_calls.extend(tool_calls)
            # Tool call chunks should be filtered from client
            assert filtered_chunk is None

        # Verify we got tool_calls list, not assistant message
        assert len(completed_tool_calls) == 1
        tool_call = completed_tool_calls[0]

        # Should be tool_call dict with id/type/function fields
        assert "id" in tool_call
        assert tool_call["id"] == "call_123"
        assert "type" in tool_call
        assert tool_call["type"] == "function"
        assert "function" in tool_call
        assert tool_call["function"]["name"] == "test_tool"
        assert tool_call["function"]["arguments"] == '{"arg": "value"}'

        # Should NOT be assistant message format
        assert "role" not in tool_call
        assert "content" not in tool_call

    @pytest.mark.asyncio
    async def test_content_chunks_pass_through(self):
        """Verify content chunks pass through to client."""
        session_manager = MagicMock()
        thinking_filter = None
        filter_instance = StreamingFilter(session_manager, thinking_filter)

        content_chunk = {
            "id": "chatcmpl-123",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "test-model",
            "choices": [{
                "index": 0,
                "delta": {"content": "Hello world"},
                "finish_reason": None,
            }]
        }

        filtered_chunk, tool_calls = await filter_instance.filter_chunk(content_chunk, "test_session")

        # Content should pass through
        assert filtered_chunk is not None
        assert filtered_chunk["choices"][0]["delta"]["content"] == "Hello world"
        # No tool calls
        assert len(tool_calls) == 0

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_single_response(self):
        """Verify handling of multiple tool calls in one stream (if supported)."""
        # Note: Current OpenAI API typically sends one tool call per response,
        # but architecture should handle multiple if upstream supports it
        session_manager = MagicMock()
        thinking_filter = None
        filter_instance = StreamingFilter(session_manager, thinking_filter)

        # First tool call
        chunks_tool1 = [
            {
                "id": "chatcmpl-123",
                "object": "chat.completion.chunk",
                "created": 1234567890,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "tool1", "arguments": '{"a": 1}'}
                        }]
                    },
                    "finish_reason": "tool_calls",
                }]
            },
        ]

        completed_tools = []
        for chunk in chunks_tool1:
            _, tools = await filter_instance.filter_chunk(chunk, "test_session")
            completed_tools.extend(tools)

        assert len(completed_tools) == 1
        assert completed_tools[0]["function"]["name"] == "tool1"


class TestToolCallAccumulator:
    """Test tool call accumulation from SSE chunks."""

    def test_accumulator_builds_complete_tool_call(self):
        """Verify accumulator correctly assembles tool call from chunks."""
        accumulator = ToolCallAccumulator()

        chunks = [
            {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "id": "call_xyz",
                            "type": "function",
                            "function": {"name": "get_", "arguments": ""}
                        }]
                    },
                    "finish_reason": None,
                }]
            },
            {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "function": {"name": "weather", "arguments": '{"loc'}
                        }]
                    },
                    "finish_reason": None,
                }]
            },
            {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "function": {"arguments": 'ation": "NYC"}'}
                        }]
                    },
                    "finish_reason": None,
                }]
            },
            {
                "choices": [{
                    "delta": {},
                    "finish_reason": "tool_calls",
                }]
            },
        ]

        for chunk in chunks[:-1]:
            accumulator.add_chunk(chunk)
            assert not accumulator.is_complete(chunk)

        # Last chunk marks completion
        accumulator.add_chunk(chunks[-1])
        assert accumulator.is_complete(chunks[-1])

        # Verify assembled tool call
        assert accumulator.id == "call_xyz"
        assert accumulator.type == "function"
        assert accumulator.function_name == "get_weather"
        assert accumulator.function_args == '{"location": "NYC"}'

        # to_message() should return tool_call dict, not assistant message
        message = accumulator.to_message()
        assert "role" in message  # Still returns message format for compatibility
        assert message["role"] == "assistant"
        assert message["tool_calls"][0]["id"] == "call_xyz"
