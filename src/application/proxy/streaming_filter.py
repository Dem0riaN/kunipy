"""Streaming filter for real-time SSE chunk processing.

Filters tool calls from streaming responses in real-time,
providing true incremental streaming without buffering.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.thinking_filter import ThinkingFilter
    from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class StreamState(Enum):
    """State machine for streaming filter."""

    CONTENT = "content"  # Regular content streaming
    TOOL_CALL = "tool_call"  # Accumulating tool call chunks
    TOOL_RESULT = "tool_result"  # Tool execution result


@dataclass
class ToolCallAccumulator:
    """Accumulates tool call chunks until complete."""

    id: str = ""
    type: str = ""
    function_name: str = ""
    function_args: str = ""
    chunks: list[dict] = field(default_factory=list)

    def add_chunk(self, chunk: dict) -> None:
        """Add chunk to accumulator."""
        self.chunks.append(chunk)

        # Extract tool call delta
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        tool_calls = delta.get("tool_calls", [])

        if tool_calls:
            tool = tool_calls[0]

            # Accumulate id
            if "id" in tool:
                self.id = tool["id"]

            # Accumulate type
            if "type" in tool:
                self.type = tool["type"]

            # Accumulate function data
            if "function" in tool:
                func = tool["function"]
                if "name" in func:
                    self.function_name += func["name"]
                if "arguments" in func:
                    self.function_args += func["arguments"]

    def is_complete(self, chunk: dict) -> bool:
        """Check if tool call is complete (finish_reason present)."""
        choices = chunk.get("choices", [])
        if not choices:
            return False

        finish_reason = choices[0].get("finish_reason")
        return finish_reason == "tool_calls"

    def to_message(self) -> dict:
        """Convert accumulated tool call to message format."""
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": self.id,
                "type": self.type,
                "function": {
                    "name": self.function_name,
                    "arguments": self.function_args
                }
            }]
        }


class StreamingFilter:
    """Filters SSE chunks in real-time, hiding tool calls and thinking from client.

    Provides true incremental streaming by processing chunks one-by-one
    without buffering the entire response. Integrates ThinkingFilter to
    strip JSON structure from streaming content.
    """

    def __init__(self, session_manager: SessionManager, thinking_filter: ThinkingFilter | None = None):
        """Initialize streaming filter.

        Args:
            session_manager: Session manager for storing hidden context
            thinking_filter: Optional ThinkingFilter for content filtering
        """
        self._session_manager = session_manager
        self._thinking_filter = thinking_filter
        self._state = StreamState.CONTENT
        self._tool_accumulator: ToolCallAccumulator | None = None
        self._content_buffer = ""  # Buffer for thinking filter
        logger.debug("StreamingFilter initialized")

    async def filter_chunk(
        self,
        chunk: dict,
        session_id: str
    ) -> tuple[dict | None, list[dict]]:
        """Filter single SSE chunk in real-time.

        Args:
            chunk: SSE chunk from upstream
            session_id: Session ID for context storage

        Returns:
            Tuple of (client_chunk, hidden_messages):
            - client_chunk: None if filtered, chunk if passed through
            - hidden_messages: Tool calls extracted from stream
        """
        # Check if chunk contains tool call
        if self._is_tool_call_chunk(chunk):
            return await self._handle_tool_call_chunk(chunk, session_id)

        # Apply thinking filter to content chunks if configured
        if self._thinking_filter:
            chunk = self._apply_thinking_filter(chunk)

        # Regular content chunk - pass through
        return chunk, []

    def _is_tool_call_chunk(self, chunk: dict) -> bool:
        """Detect if chunk contains tool_calls field.

        Args:
            chunk: SSE chunk

        Returns:
            True if chunk is part of tool call
        """
        choices = chunk.get("choices", [])
        if not choices:
            return False

        delta = choices[0].get("delta", {})

        # Tool call detected
        if "tool_calls" in delta:
            return True

        # Check finish_reason for tool_calls
        finish_reason = choices[0].get("finish_reason")
        return finish_reason == "tool_calls"

    async def _handle_tool_call_chunk(
        self,
        chunk: dict,
        session_id: str
    ) -> tuple[None, list[dict]]:
        """Handle tool call chunk accumulation.

        Args:
            chunk: Tool call chunk
            session_id: Session ID

        Returns:
            (None, hidden_messages) - filtered from client
        """
        # Initialize accumulator on first tool chunk
        if self._tool_accumulator is None:
            self._tool_accumulator = ToolCallAccumulator()
            self._state = StreamState.TOOL_CALL
            logger.debug(f"Started tool call accumulation for session {session_id}")

        # Add chunk to accumulator
        self._tool_accumulator.add_chunk(chunk)

        # Check if tool call complete
        if self._tool_accumulator.is_complete(chunk):
            # Convert to message and return as hidden
            tool_message = self._tool_accumulator.to_message()
            hidden_messages = [tool_message]

            logger.info(
                f"Tool call complete: {self._tool_accumulator.function_name} "
                f"(session {session_id})"
            )

            # Reset accumulator
            self._tool_accumulator = None
            self._state = StreamState.CONTENT

            return None, hidden_messages

        # Tool call incomplete - continue accumulating
        return None, []

    def _apply_thinking_filter(self, chunk: dict) -> dict:
        """Apply thinking filter to content chunk.

        Buffers content and attempts to parse/filter JSON structure.
        Returns modified chunk with filtered content.

        Args:
            chunk: Content chunk

        Returns:
            Modified chunk with filtered content
        """
        choices = chunk.get("choices", [])
        if not choices:
            return chunk

        delta = choices[0].get("delta", {})
        content = delta.get("content", "")

        if not content:
            return chunk

        # Add to buffer
        self._content_buffer += content

        # Check if buffer contains complete JSON structure
        stripped = self._content_buffer.strip()

        # Detect JSON structure start - only buffer if we see the thinking pattern
        if stripped.startswith("{"):
            # Check if this looks like our JSON format
            has_thinking = '"thinking"' in stripped or "'thinking'" in stripped
            has_response = '"response"' in stripped or "'response'" in stripped

            # Early suppression: if we see "{" start, suppress immediately until we determine it's not JSON
            if not has_thinking and len(stripped) < 20:
                # Too early to tell - suppress this chunk
                empty_chunk = {
                    "id": chunk["id"],
                    "object": chunk["object"],
                    "created": chunk["created"],
                    "model": chunk["model"],
                    "choices": [{
                        "index": 0,
                        "delta": {"content": ""},
                        "finish_reason": None
                    }]
                }
                return empty_chunk

            if has_thinking and has_response:
                # Try to parse as complete JSON
                try:
                    data = json.loads(stripped)
                    # Successfully parsed - extract response field
                    response_text = data.get("response", "")

                    if response_text:
                        # Create new chunk with only the response text
                        filtered_chunk = {
                            "id": chunk["id"],
                            "object": chunk["object"],
                            "created": chunk["created"],
                            "model": chunk["model"],
                            "choices": [{
                                "index": 0,
                                "delta": {"content": response_text},
                                "finish_reason": choices[0].get("finish_reason")
                            }]
                        }

                        logger.info(f"[STREAMING] Filtered thinking from JSON: {len(self._content_buffer)} → {len(response_text)} chars")

                        # Clear buffer
                        self._content_buffer = ""

                        return filtered_chunk

                except json.JSONDecodeError:
                    # Incomplete JSON - suppress this chunk and keep buffering
                    empty_chunk = {
                        "id": chunk["id"],
                        "object": chunk["object"],
                        "created": chunk["created"],
                        "model": chunk["model"],
                        "choices": [{
                            "index": 0,
                            "delta": {"content": ""},
                            "finish_reason": None  # Don't propagate finish_reason while buffering
                        }]
                    }
                    return empty_chunk

            elif has_thinking:
                # We see thinking but not response yet - suppress and keep buffering
                empty_chunk = {
                    "id": chunk["id"],
                    "object": chunk["object"],
                    "created": chunk["created"],
                    "model": chunk["model"],
                    "choices": [{
                        "index": 0,
                        "delta": {"content": ""},
                        "finish_reason": None  # Don't propagate finish_reason while buffering
                    }]
                }
                return empty_chunk

        # No JSON pattern detected - pass through unchanged
        return chunk

    def reset(self) -> None:
        """Reset filter state between requests."""
        self._state = StreamState.CONTENT
        self._tool_accumulator = None
        self._content_buffer = ""
