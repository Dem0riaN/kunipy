"""Fallback parser for text-based tool calls.

Some LLMs (like DeepSeek-R1) output tool calls as text instead of structured JSON.
This parser extracts tool calls from plain text responses and converts them to
the standard tool_calls format.

Example input:
    send_telegram_message({"text": "Hello!"})
    open_chat_by_id({"chat_id": 123})

Example output:
    [
        {"id": "call_1", "function": {"name": "send_telegram_message", "arguments": '{"text": "Hello!"}'}},
        {"id": "call_2", "function": {"name": "open_chat_by_id", "arguments": '{"chat_id": 123}'}}
    ]
"""

import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class ToolCallParser:
    """Parses text-based tool calls into structured format.

    Handles cases where LLMs output tool calls as plain text instead of
    using native function calling API.
    """

    # Pattern: function_name({"key": "value"})
    # Matches tool calls in format: tool_name({json_object})
    TOOL_CALL_PATTERN = re.compile(
        r'([a-z_][a-z0-9_]*)\s*\(\s*(\{[^}]*\})\s*\)',
        re.IGNORECASE
    )

    def __init__(self) -> None:
        """Initialize parser."""
        self._call_counter = 0

    def parse_text_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Extract tool calls from plain text.

        Args:
            text: Plain text containing tool calls in format: tool_name({"arg": "value"})

        Returns:
            List of tool call dictionaries in OpenAI format

        Example:
            >>> parser = ToolCallParser()
            >>> text = 'send_telegram_message({"text": "Hi!"})'
            >>> calls = parser.parse_text_tool_calls(text)
            >>> calls[0]["function"]["name"]
            'send_telegram_message'
        """
        if not text:
            return []

        tool_calls = []
        matches = self.TOOL_CALL_PATTERN.finditer(text)

        for match in matches:
            function_name = match.group(1)
            arguments_str = match.group(2)

            # Validate JSON arguments
            try:
                # Try to parse JSON to validate it
                json.loads(arguments_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Skipping malformed tool call {function_name}: invalid JSON arguments. "
                    f"Error: {e}"
                )
                continue

            # Generate unique call ID
            self._call_counter += 1
            call_id = f"call_{uuid.uuid4().hex[:8]}_{self._call_counter}"

            # Create tool call in OpenAI format
            tool_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": arguments_str
                }
            }
            tool_calls.append(tool_call)

            logger.debug(
                f"Parsed text-based tool call: {function_name} with args {arguments_str[:100]}"
            )

        return tool_calls

    def extract_thinking_and_calls(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Split text into thinking content and tool calls.

        Args:
            text: Plain text potentially containing thinking + tool calls

        Returns:
            Tuple of (thinking_text, tool_calls_list)

        Example:
            >>> parser = ToolCallParser()
            >>> text = "I should reply.\\nsend_telegram_message({\"text\": \"Hi!\"})"
            >>> thinking, calls = parser.extract_thinking_and_calls(text)
            >>> thinking
            'I should reply.'
            >>> len(calls)
            1
        """
        if not text:
            return ("", [])

        # Extract tool calls
        tool_calls = self.parse_text_tool_calls(text)

        if not tool_calls:
            # No tool calls found - entire text is thinking
            return (text, [])

        # Remove tool call text, keep only thinking
        thinking_text = text
        for match in self.TOOL_CALL_PATTERN.finditer(text):
            thinking_text = thinking_text.replace(match.group(0), "")

        # Clean up extra whitespace
        thinking_text = "\n".join(
            line.strip() for line in thinking_text.split("\n") if line.strip()
        )

        return (thinking_text.strip(), tool_calls)

    def is_text_based_tool_call(self, text: str) -> bool:
        """Check if text contains text-based tool calls.

        Args:
            text: Text to check

        Returns:
            True if text contains tool call patterns

        Example:
            >>> parser = ToolCallParser()
            >>> parser.is_text_based_tool_call('send_telegram_message({"text": "Hi"})')
            True
            >>> parser.is_text_based_tool_call('Just thinking...')
            False
        """
        if not text:
            return False
        return bool(self.TOOL_CALL_PATTERN.search(text))


# Global parser instance (stateless, thread-safe)
_parser = ToolCallParser()


def parse_text_tool_calls(text: str) -> list[dict[str, Any]]:
    """Parse text-based tool calls into structured format.

    Convenience function for quick parsing without creating parser instance.

    Args:
        text: Plain text containing tool calls

    Returns:
        List of tool call dictionaries

    Example:
        >>> from infrastructure.tool_call_parser import parse_text_tool_calls
        >>> calls = parse_text_tool_calls('send_telegram_message({"text": "Hello"})')
        >>> len(calls)
        1
    """
    return _parser.parse_text_tool_calls(text)


def extract_thinking_and_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Extract thinking and tool calls from text.

    Convenience function for quick extraction without creating parser instance.

    Args:
        text: Plain text with thinking and tool calls

    Returns:
        Tuple of (thinking_text, tool_calls)

    Example:
        >>> from infrastructure.tool_call_parser import extract_thinking_and_calls
        >>> thinking, calls = extract_thinking_and_calls('Thinking...\\nsend_telegram_message({"text": "Hi"})')
        >>> len(calls)
        1
    """
    return _parser.extract_thinking_and_calls(text)
