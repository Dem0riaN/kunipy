"""Telegram operation tools for LLM function calling.

Provides tools for sending, editing, deleting messages, managing chats, and searching.
"""

import asyncio
import logging
import random
from typing import Any

from ...config import get_config
from ...telegram_client import TelegramChat, TelegramClient
from .registry import Tool, ToolContext

logger = logging.getLogger(__name__)


def register_telegram_tools(
    registry: Any,
    telegram: TelegramClient,
    current_chat: TelegramChat | None = None,
    recent_bot_messages: list[str] | None = None,
) -> None:
    """Register all Telegram-related tools.

    Args:
        registry: ToolRegistry instance
        telegram: Telegram client
        current_chat: Current chat context
        recent_bot_messages: Recent bot messages for anti-repeat check
    """
    from ..anti_repeat_service import AntiRepeatConfig, AntiRepeatService

    config = get_config()
    anti_repeat_config = AntiRepeatConfig(
        enabled=True,
        max_history=config.anti_repeat_max_history,
        trigger_max=config.anti_repeat_trigger_max,
        trigger_avg=config.anti_repeat_trigger_avg,
    )
    anti_repeat_service = AntiRepeatService(anti_repeat_config)

    # Send message tool
    async def _send_message(ctx: ToolContext) -> Any:
        text = ctx.args["text"]
        current_chat_id = current_chat.id if current_chat else 0
        requested_chat_id = ctx.args.get("chat_id")

        if requested_chat_id and current_chat_id and requested_chat_id != current_chat_id:
            title = current_chat.title if current_chat else str(current_chat_id)
            return (
                f'Error: you can\'t send messages to other chats. Open them first. '
                f'You are currently in chat "{title}" (chat_id={current_chat_id}).'
            )
        chat_id = requested_chat_id or current_chat_id

        reply_to = ctx.args.get("reply_to")
        if reply_to and chat_id:
            recent_history = await telegram.get_chat_history(chat_id, limit=30)
            if not any(m.id == reply_to for m in recent_history):
                return (
                    "Error: you are trying to reply to a message that isn't in this chat's recent "
                    "history. Don't guess message IDs -- only reply_to a message_id you actually saw "
                    "in this conversation, or omit reply_to."
                )

        repeat_warning = anti_repeat_service.check_repetition(text, recent_bot_messages)
        if repeat_warning:
            return repeat_warning

        await _simulate_typing(telegram, chat_id, text)
        return await telegram.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to,
        )

    registry.register(
        name="send_telegram_message",
        tool=Tool(
            type="function",
            function={
                "name": "send_telegram_message",
                "description": "Send a message to the current or specified Telegram chat.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The message text to send"},
                        "chat_id": {"type": "integer", "description": "Optional: target chat ID. If omitted, uses current chat."},
                        "reply_to": {"type": "integer", "description": "Optional: message ID to reply to"},
                    },
                    "required": ["text"],
                },
            },
        ),
        handler=_send_message,
    )

    # React to message tool
    async def _react_to_message(ctx: ToolContext) -> Any:
        chat_id = ctx.args.get("chat_id") or (current_chat.id if current_chat else 0)
        message_id = ctx.args["message_id"]
        emoji = ctx.args["emoji"]

        if not chat_id:
            return "Error: no chat_id available."

        try:
            await telegram.react_with_emoji(chat_id, message_id, emoji)
            return f"Reacted with {emoji} to message {message_id}."
        except Exception as e:
            logger.error(f"Failed to send reaction: {e}")
            return f"Error: failed to react ({e})"

    registry.register(
        name="react_to_message",
        tool=Tool(
            type="function",
            function={
                "name": "react_to_message",
                "description": "React to a message with an emoji. Use this to express emotions without sending text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "integer", "description": "Message ID to react to"},
                        "emoji": {"type": "string", "description": "Emoji to react with (e.g., '👍', '❤️', '😂')"},
                        "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
                    },
                    "required": ["message_id", "emoji"],
                },
            },
        ),
        handler=_react_to_message,
    )

    # Get chats tool
    async def _get_chats(ctx: ToolContext) -> Any:
        return await telegram.get_chats(limit=ctx.args.get("limit", 50))

    registry.register(
        name="get_telegram_chats",
        tool=Tool(
            type="function",
            function={
                "name": "get_telegram_chats",
                "description": "Retrieve a list of your Telegram chats (conversations, groups, channels).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum number of chats to return", "default": 50},
                    },
                },
            },
        ),
        handler=_get_chats,
    )

    # Search chats tool
    async def _search_chats(ctx: ToolContext) -> Any:
        return await telegram.search_chats(ctx.args["query"])

    registry.register(
        name="search_chats",
        tool=Tool(
            type="function",
            function={
                "name": "search_chats",
                "description": "Search for chats by name or title.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string"},
                    },
                    "required": ["query"],
                },
            },
        ),
        handler=_search_chats,
    )

    # Search messages tool
    async def _search_messages(ctx: ToolContext) -> Any:
        return await telegram.search_messages(
            chat_id=ctx.args.get("chat_id"),
            query=ctx.args["query"],
            limit=ctx.args.get("limit", 10),
        )

    registry.register(
        name="search_messages",
        tool=Tool(
            type="function",
            function={
                "name": "search_messages",
                "description": "Search for messages in a specific chat or globally.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string"},
                        "chat_id": {"type": "integer", "description": "Optional: limit search to this chat"},
                        "limit": {"type": "integer", "description": "Maximum results", "default": 10},
                    },
                    "required": ["query"],
                },
            },
        ),
        handler=_search_messages,
    )

    # Open chat tool
    async def _open_chat(ctx: ToolContext) -> Any:
        return await telegram.open_chat(ctx.args["chat_id"])

    registry.register(
        name="open_chat_by_id",
        tool=Tool(
            type="function",
            function={
                "name": "open_chat_by_id",
                "description": "Open a Telegram chat by its ID. This loads recent messages and makes the chat current.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "The chat ID to open"},
                    },
                    "required": ["chat_id"],
                },
            },
        ),
        handler=_open_chat,
    )

    # Edit message tool
    async def _edit_message(ctx: ToolContext) -> Any:
        return await telegram.edit_message(
            chat_id=ctx.args["chat_id"],
            message_id=ctx.args["message_id"],
            text=ctx.args["text"],
        )

    registry.register(
        name="edit_telegram_message",
        tool=Tool(
            type="function",
            function={
                "name": "edit_telegram_message",
                "description": "Edit a previously sent message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Chat ID"},
                        "message_id": {"type": "integer", "description": "Message ID to edit"},
                        "text": {"type": "string", "description": "New message text"},
                    },
                    "required": ["chat_id", "message_id", "text"],
                },
            },
        ),
        handler=_edit_message,
    )

    # Delete message tool
    async def _remove_message(ctx: ToolContext) -> Any:
        return await telegram.delete_message(
            chat_id=ctx.args["chat_id"],
            message_id=ctx.args["message_id"],
        )

    registry.register(
        name="remove_telegram_message",
        tool=Tool(
            type="function",
            function={
                "name": "remove_telegram_message",
                "description": "Delete a message from a chat.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Chat ID"},
                        "message_id": {"type": "integer", "description": "Message ID to delete"},
                    },
                    "required": ["chat_id", "message_id"],
                },
            },
        ),
        handler=_remove_message,
    )

    # React with emoji tool
    async def _react_emoji(ctx: ToolContext) -> Any:
        return await telegram.react_to_message(
            chat_id=ctx.args["chat_id"],
            message_id=ctx.args["message_id"],
            emoji=ctx.args["emoji"],
        )

    registry.register(
        name="react_with_emoji",
        tool=Tool(
            type="function",
            function={
                "name": "react_with_emoji",
                "description": "React to a message with an emoji.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "integer", "description": "Chat ID"},
                        "message_id": {"type": "integer", "description": "Message ID to react to"},
                        "emoji": {"type": "string", "description": "Emoji to react with"},
                    },
                    "required": ["chat_id", "message_id", "emoji"],
                },
            },
        ),
        handler=_react_emoji,
    )

    # Forward message tool
    async def _forward_message(ctx: ToolContext) -> Any:
        return await telegram.forward_message(
            from_chat_id=ctx.args["from_chat_id"],
            to_chat_id=ctx.args["to_chat_id"],
            message_id=ctx.args["message_id"],
        )

    registry.register(
        name="forward_message",
        tool=Tool(
            type="function",
            function={
                "name": "forward_message",
                "description": "Forward a message from one chat to another.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "from_chat_id": {"type": "integer", "description": "Source chat ID"},
                        "to_chat_id": {"type": "integer", "description": "Destination chat ID"},
                        "message_id": {"type": "integer", "description": "Message ID to forward"},
                    },
                    "required": ["from_chat_id", "to_chat_id", "message_id"],
                },
            },
        ),
        handler=_forward_message,
    )

    # Join chat tool
    if config.can_join_chats:
        async def _join_chat(ctx: ToolContext) -> Any:
            return await telegram.join_chat(ctx.args["invite_link"])

        registry.register(
            name="join_chat",
            tool=Tool(
                type="function",
                function={
                    "name": "join_chat",
                    "description": "Join a Telegram chat via invite link.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "invite_link": {"type": "string", "description": "Chat invite link"},
                        },
                        "required": ["invite_link"],
                    },
                },
            ),
            handler=_join_chat,
        )

    # Leave chat tool
    if config.can_leave_chats:
        async def _leave_chat(ctx: ToolContext) -> Any:
            return await telegram.leave_chat(ctx.args["chat_id"])

        registry.register(
            name="leave_chat",
            tool=Tool(
                type="function",
                function={
                    "name": "leave_chat",
                    "description": "Leave a Telegram chat.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chat_id": {"type": "integer", "description": "Chat ID to leave"},
                        },
                        "required": ["chat_id"],
                    },
                },
            ),
            handler=_leave_chat,
        )


async def _simulate_typing(telegram: TelegramClient, chat_id: int, text: str) -> None:
    """Show typing indicator for duration proportional to message length."""
    if not chat_id or not text:
        return
    config = get_config()
    min_wpm = max(config.typing_simulation_min_wpm, 1)
    max_wpm = max(config.typing_simulation_max_wpm, min_wpm)
    wpm = random.uniform(min_wpm, max_wpm)

    word_count = max(len(text.split()), 1)
    duration = min((word_count / wpm) * 60.0, 8.0)

    try:
        await telegram.send_typing(chat_id)
        if duration > 0.1:
            await asyncio.sleep(duration)
    except (ValueError, TypeError) as e:
        logger.debug(f"Typing simulation failed (non-fatal): {e}")
