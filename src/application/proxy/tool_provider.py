"""Tool provider for proxy server.

Управляет инструментами доступными через прокси.
Следует registry pattern из application.tools.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...application.tools import Tool, ToolContext, ToolRegistry
from ...config import Config
from ...openai_chat import Message

if TYPE_CHECKING:
    from ...diary import Diary
    from ...openai_chat import OpenAIChat

logger = logging.getLogger(__name__)


class ProxyToolProvider:
    """Provides tools for proxy server.

    Responsibilities:
    - Build tool registry with allowed tools only
    - Provide tool definitions for LLM
    - Execute tool calls
    - Maintain separation from main worker tools

    Прокси использует ограниченный набор инструментов:
    - ask (diary query) - если diary enabled
    - web_search - если web_search enabled

    Telegram tools и admin tools не доступны через прокси.
    """

    def __init__(self, config: Config, diary: Diary | None, openai: OpenAIChat):
        """Initialize tool provider.

        Args:
            config: Application configuration
            diary: Diary instance (optional)
            openai: OpenAI client for LLM operations
        """
        self._config = config
        self._diary = diary
        self._openai = openai
        self._registry = self._build_registry()

        tool_names = [t.function["name"] for t in self._registry.get_tool_definitions() if t.function]
        logger.info(f"ProxyToolProvider initialized with tools: {', '.join(tool_names) if tool_names else 'none'}")

    def _build_registry(self) -> ToolRegistry:
        """Build tool registry with proxy-allowed tools.

        Returns:
            Configured ToolRegistry
        """
        from ...application.tools.memory_tools import register_memory_tools
        from ...application.tools.utilities import register_utility_tools

        registry = ToolRegistry()

        # Memory tools (ask)
        if self._diary:
            register_memory_tools(registry, self._diary, self._openai)
            logger.debug("Registered memory tools (ask)")

        # Utility tools (web_search)
        register_utility_tools(registry)
        logger.debug("Registered utility tools")

        return registry

    def get_tool_definitions(self) -> list[Tool]:
        """Get tool definitions for LLM API.

        Returns:
            List of tool definitions
        """
        return self._registry.get_tool_definitions()

    def get_tool_schemas(self) -> list[dict] | None:
        """Get tool schemas in OpenAI format.

        Returns:
            List of tool schemas or None if no tools
        """
        tools = self.get_tool_definitions()
        if not tools:
            return None

        return [tool.to_dict() for tool in tools]

    async def execute_tool_calls(
        self,
        tool_calls: list[dict],
        conversation_history: list[Message],
    ) -> list[Message]:
        """Execute multiple tool calls.

        Args:
            tool_calls: List of tool calls from LLM
            conversation_history: Current conversation history

        Returns:
            List of tool result messages
        """
        context = ToolContext(
            args={},  # Will be overridden per tool
            logger=logger,
            conversation_history=conversation_history,
            all_tool_calls=tool_calls,
        )

        return await self._registry.handle_tool_calls(tool_calls, context)

    def get_tool_count(self) -> int:
        """Get number of registered tools.

        Returns:
            Tool count
        """
        return len(self.get_tool_definitions())
