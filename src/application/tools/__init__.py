"""Tool system for LLM function calling.

Provides a modular, extensible registry-based architecture for managing tools.
"""

from .registry import Tool, ToolContext, ToolHandler, ToolRegistry
from .utilities import TERMINAL_TOOL_NAMES

__all__ = [
    "TERMINAL_TOOL_NAMES",
    "Tool",
    "ToolContext",
    "ToolHandler",
    "ToolRegistry",
    "create_default_registry",
]


def create_default_registry(
    telegram,
    diary,
    openai,
    current_chat=None,
    is_admin: bool = False,
    recent_bot_messages: list[str] | None = None,
) -> ToolRegistry:
    """Create a registry with default tools loaded.

    Args:
        telegram: TelegramClient instance
        diary: Diary instance
        openai: OpenAIChat instance
        current_chat: Current chat context
        is_admin: Whether user has admin privileges
        recent_bot_messages: Recent bot messages for anti-repeat

    Returns:
        Configured ToolRegistry instance
    """
    from .admin_tools import register_admin_tools
    from .media_tools import register_media_tools
    from .memory_tools import register_memory_tools
    from .telegram_tools import register_telegram_tools
    from .utilities import register_utility_tools

    # Create new registry
    registry = ToolRegistry()

    # Register all tool categories
    register_telegram_tools(
        registry,
        telegram=telegram,
        current_chat=current_chat,
        recent_bot_messages=recent_bot_messages,
    )

    register_memory_tools(
        registry,
        diary=diary,
        openai=openai,
    )

    register_media_tools(
        registry,
        telegram=telegram,
        openai=openai,
        current_chat=current_chat,
    )

    if is_admin:
        register_admin_tools(
            registry,
            telegram=telegram,
        )

    register_utility_tools(registry)

    return registry
