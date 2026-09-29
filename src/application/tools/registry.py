"""Tool registration and execution system.

Manages LLM function calling tools following the registry pattern.
Inspired by MediaExtractorRegistry architecture.
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from ...openai_chat import Message

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """Tool definition for LLM function calling."""

    type: str = "function"
    function: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert tool to OpenAI API format.

        Returns:
            Tool definition as dict
        """
        return {
            "type": self.type,
            "function": self.function,
        }


@dataclass
class ToolContext:
    """Context passed to tool handlers.

    Contains all dependencies and state needed for tool execution.
    """

    args: dict[str, Any]
    logger: logging.Logger
    conversation_history: list[Message]
    all_tool_calls: list[dict[str, Any]] | None = None


class ToolHandler(Protocol):
    """Protocol for tool handler functions."""

    async def __call__(self, ctx: ToolContext) -> str | dict:
        """Execute tool with given context.

        Args:
            ctx: Tool execution context

        Returns:
            Tool result as string or dict
        """
        ...


class ToolRegistry:
    """Registry for LLM tools with extensible registration.

    Responsibilities:
    - Register tools with their handlers
    - Provide tool definitions for LLM API
    - Execute tool calls
    - Handle multiple tool calls in sequence

    Uses simple strategy pattern similar to MediaExtractorRegistry.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._tools: dict[str, Tool] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, tool: Tool, handler: ToolHandler) -> None:
        """Register tool with handler.

        Args:
            name: Tool name (must match function.name in tool definition)
            tool: Tool definition for LLM API
            handler: Async function to execute tool
        """
        self._tools[name] = tool
        self._handlers[name] = handler
        logger.debug(f"Registered tool: {name}")

    def get_tool_definitions(self) -> list[Tool]:
        """Get all tools for LLM API.

        Returns:
            List of tool definitions
        """
        return list(self._tools.values())

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> str | dict:
        """Execute single tool.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments from LLM
            context: Execution context

        Returns:
            Tool result

        Raises:
            KeyError: If tool not registered
        """
        if tool_name not in self._handlers:
            error_msg = f"Tool '{tool_name}' not registered"
            logger.error(error_msg)
            raise KeyError(error_msg)

        handler = self._handlers[tool_name]
        logger.debug(f"Executing tool: {tool_name}")

        try:
            # Create context with tool arguments
            tool_ctx = ToolContext(
                args=arguments,
                logger=context.logger,
                conversation_history=context.conversation_history,
                all_tool_calls=context.all_tool_calls,
            )
            return await handler(tool_ctx)
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed")
            return f"Error executing {tool_name}: {e}"

    async def handle_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        context: ToolContext,
    ) -> list[Message]:
        """Execute multiple tool calls, return tool messages.

        Args:
            tool_calls: List of tool call dicts from LLM response
            context: Execution context

        Returns:
            List of tool response messages
        """
        tool_messages = []

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_call_id = tool_call["id"]
            arguments = tool_call["function"]["arguments"]

            # Parse arguments if they're a JSON string
            import json
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse arguments for {tool_name}: {arguments}")
                    arguments = {}

            # Execute tool
            result = await self.execute(tool_name, arguments, context)

            # Convert result to string if needed
            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False)

            # Create tool message
            tool_messages.append(
                Message(
                    role="tool",
                    content=str(result),
                    tool_call_id=tool_call_id,
                )
            )

        return tool_messages
