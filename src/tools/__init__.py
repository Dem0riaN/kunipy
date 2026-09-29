"""Backward compatibility module for old tools.py imports.

This module preserves the original tools.py API while the codebase
transitions to the new application.tools registry-based system.

DEPRECATED: Import from src.application.tools instead.
"""

from pathlib import Path

from ..application.tools import Tool, ToolContext

# Re-export core classes for backward compatibility
__all__ = ["OpenAITools", "Tool", "ToolContext", "create_default_tools"]

# Load tools.py from parent src/ directory (renamed to tools_old_backup.py)
tools_path = Path(__file__).parent.parent / "tools_old_backup.py"
if tools_path.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("src.tools_old", str(tools_path))
    if spec and spec.loader:
        tools_old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools_old)

        # Re-export from old module
        OpenAITools = tools_old.OpenAITools
        create_default_tools = tools_old.create_default_tools
        _TERMINAL_TOOL_NAMES = tools_old._TERMINAL_TOOL_NAMES
        _check_anti_repeat = tools_old._check_anti_repeat
        create_ask_tool = tools_old.create_ask_tool
        create_web_search_tool = tools_old.create_web_search_tool
        create_join_chat_tool = tools_old.create_join_chat_tool
        create_leave_chat_tool = tools_old.create_leave_chat_tool
        create_send_telegram_message_tool = tools_old.create_send_telegram_message_tool
