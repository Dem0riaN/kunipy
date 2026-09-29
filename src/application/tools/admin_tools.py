"""Admin tools for group management in Telegram.

Provides tools for banning users, removing messages, and setting member roles.
"""

import logging
from typing import Any

from ...telegram_client import TelegramClient
from .registry import Tool, ToolContext

logger = logging.getLogger(__name__)


def register_admin_tools(
    registry: Any,
    telegram: TelegramClient,
) -> None:
    """Register admin-only tools for group management.

    Args:
        registry: ToolRegistry instance
        telegram: Telegram client
    """

    # Ban user tool
    async def _ban_user(ctx: ToolContext) -> str:
        ok = await telegram.ban_chat_member(ctx.args["chat_id"], ctx.args["user_id"])
        if ok:
            return f"Banned user {ctx.args['user_id']} from chat {ctx.args['chat_id']}."
        return f"Error: failed to ban user {ctx.args['user_id']} (missing rights or invalid IDs)."

    registry.register(
        name="group_admin_ban_user",
        tool=Tool(
            type="function",
            function={
                "name": "group_admin_ban_user",
                "description": "Ban a user from a group (admin only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Group chat ID"},
                        "user_id": {"type": "integer", "description": "User ID to ban"},
                    },
                    "required": ["chat_id", "user_id"],
                },
            },
        ),
        handler=_ban_user,
    )

    # Remove message tool
    async def _remove_message(ctx: ToolContext) -> str:
        await telegram.delete_message(ctx.args["chat_id"], ctx.args["message_id"])
        return f"Removed message {ctx.args['message_id']} from chat {ctx.args['chat_id']}."

    registry.register(
        name="group_admin_remove_message",
        tool=Tool(
            type="function",
            function={
                "name": "group_admin_remove_message",
                "description": "Remove a message from a group (admin only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Group chat ID"},
                        "message_id": {"type": "integer", "description": "Message ID to remove"},
                    },
                    "required": ["chat_id", "message_id"],
                },
            },
        ),
        handler=_remove_message,
    )

    # Set user tag/role tool
    async def _set_user_tag(ctx: ToolContext) -> str:
        ok = await telegram.set_member_tag(ctx.args["chat_id"], ctx.args["user_id"], ctx.args["tag"])
        if ok:
            return f"Set tag '{ctx.args['tag']}' for user {ctx.args['user_id']} in chat {ctx.args['chat_id']}."
        return f"Error: failed to set tag for user {ctx.args['user_id']} (missing rights or invalid IDs)."

    registry.register(
        name="group_admin_set_user_tag",
        tool=Tool(
            type="function",
            function={
                "name": "group_admin_set_user_tag",
                "description": (
                    "Set a role for a user in a group (admin only). "
                    "tag='admin' or 'moderator' promotes to administrator; any other value demotes to a plain member."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Group chat ID"},
                        "user_id": {"type": "integer", "description": "User ID"},
                        "tag": {"type": "string", "description": "Tag to assign (e.g., 'member', 'moderator', 'admin')"},
                    },
                    "required": ["chat_id", "user_id", "tag"],
                },
            },
        ),
        handler=_set_user_tag,
    )
