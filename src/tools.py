"""Tool definitions for LLM function calling.

Provides the OpenAITools container and individual tool handlers for:
- Telegram operations (send message, get chats, search, etc.)
- Diary operations (ask/query)
- Media generation (photo, audio)
- Web search
- Administrative tools
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .config import get_config
from .diary import Diary
from .openai_chat import OpenAIChat, Message
from .telegram_client import TelegramClient, TelegramChat, TelegramMessage

logger = logging.getLogger(__name__)


class ToolContext:
    """Context passed to tool handlers."""

    def __init__(
        self,
        args: Dict[str, Any],
        logger: logging.Logger,
        temporary_context: List[Message],
        all_tool_calls: Optional[List[Dict[str, Any]]] = None,
    ):
        self.args = args
        self.logger = logger
        self.temporary_context = temporary_context
        self.all_tool_calls = all_tool_calls or []


class Tool:
    """A single tool definition with handler."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[[ToolContext], Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class OpenAITools:
    """Container for all tools available to the LLM."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def insert(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def to_json_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas for OpenAI API."""
        return [t.to_json_schema() for t in self._tools.values()]

    async def handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        temporary_context: List[Message],
    ) -> List[Message]:
        """Execute tool calls and return results as tool messages."""
        results = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool = self._tools.get(name)
            if not tool:
                results.append(Message(
                    role="tool",
                    content=f"Error: Tool '{name}' not found",
                    tool_call_id=tc.get("id"),
                ))
                continue
            try:
                ctx = ToolContext(
                    args=args,
                    logger=logger,
                    temporary_context=temporary_context,
                    all_tool_calls=tool_calls,
                )
                result = await tool.handler(ctx)
                if isinstance(result, str):
                    content = result
                else:
                    content = json.dumps(result, ensure_ascii=False)
                results.append(Message(
                    role="tool",
                    content=content,
                    tool_call_id=tc.get("id"),
                ))
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                results.append(Message(
                    role="tool",
                    content=f"Error: {str(e)}",
                    tool_call_id=tc.get("id"),
                ))
        return results


# ============================================================
# Tool factories
# ============================================================

def create_send_telegram_message_tool(
    telegram: TelegramClient,
    chat: Optional[TelegramChat] = None,
) -> Tool:
    """Send a message to a Telegram chat."""
    return Tool(
        name="send_telegram_message",
        description="Send a message to the current or specified Telegram chat.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The message text to send"},
                "chat_id": {"type": "integer", "description": "Optional: target chat ID. If omitted, uses current chat."},
                "reply_to": {"type": "integer", "description": "Optional: message ID to reply to"},
            },
            "required": ["text"],
        },
        handler=lambda ctx: telegram.send_message(
            chat_id=ctx.args.get("chat_id") or (chat.id if chat else 0),
            text=ctx.args["text"],
            reply_to_message_id=ctx.args.get("reply_to"),
        ),
    )


def create_get_telegram_chats_tool(
    telegram: TelegramClient,
) -> Tool:
    """Get list of Telegram chats."""
    return Tool(
        name="get_telegram_chats",
        description="Retrieve a list of your Telegram chats (conversations, groups, channels).",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of chats to return", "default": 50},
            },
        },
        handler=lambda ctx: telegram.get_chats(limit=ctx.args.get("limit", 50)),
    )


def create_search_chats_tool(
    telegram: TelegramClient,
) -> Tool:
    """ chats by name."""
    return Tool(
        name="_chats",
        description=" for chats by name or title.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": " query string"},
            },
            "required": ["query"],
        },
        handler=lambda ctx: telegram.search_chats(ctx.args["query"]),
    )


def create_search_messages_tool(
    telegram: TelegramClient,
) -> Tool:
    """ messages in a chat."""
    return Tool(
        name="_messages",
        description=" for messages in a specific chat or globally.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": " query string"},
                "chat_id": {"type": "integer", "description": "Optional: limit search to this chat"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 10},
            },
            "required": ["query"],
        },
        handler=lambda ctx: telegram.search_messages(
            chat_id=ctx.args.get("chat_id"),
            query=ctx.args["query"],
            limit=ctx.args.get("limit", 10),
        ),
    )


def create_open_chat_tool(
    telegram: TelegramClient,
) -> Tool:
    """Open a chat and load its history."""
    return Tool(
        name="open_chat_by_id",
        description="Open a Telegram chat by its ID. This loads recent messages and makes the chat current.",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "The ID of the Telegram chat to open"},
            },
            "required": ["chat_id"],
        },
        handler=lambda ctx: telegram.open_chat(ctx.args["chat_id"]),
    )


def create_ask_tool(
    diary: Diary,
    openai: OpenAIChat,
    max_entries: int = 5,
) -> Tool:
    """Query the diary (RAG) for relevant memories."""
    return Tool(
        name="ask",
        description=(
            "Query your diary/memory for information relevant to the current conversation. "
            "This performs a semantic search across all your stored memories and returns the most related entries."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question or topic to search for in memory"},
                "max_entries": {"type": "integer", "description": "Maximum number of entries to return", "default": 5},
            },
            "required": ["query"],
        },
        handler=lambda ctx: _handle_ask(ctx, diary, openai, max_entries),
    )


async def _handle_ask(
    ctx: ToolContext,
    diary: Diary,
    openai: OpenAIChat,
    max_entries: int,
) -> str:
    """Handler for ask tool."""
    query_text = ctx.args["query"]
    max_entries = ctx.args.get("max_entries", max_entries)

    # Get embedding for the query
    embedding = await openai.embedding(query_text)
    # Search diary
    results = await diary.query(
        embedding,
        max_entries=max_entries,
        min_relatedness=get_config().diary_min_relatedness,
    )

    if not results:
        return "No relevant memories found."

    # Format results
    output_parts = ["Related memories:\n"]
    for entry, score in results:
        output_parts.append(f"--- Entry {entry.id} (relevance: {score:.3f}) ---")
        output_parts.append(entry.body)
        output_parts.append("")
    return "\n".join(output_parts)


def create_sticker_tools(
    telegram: TelegramClient,
) -> List[Tool]:
    """Create sticker-related tools."""
    tools = []

    tools.append(Tool(
        name="sticker_send",
        description="Send a sticker to the current chat.",
        parameters={
            "type": "object",
            "properties": {
                "sticker": {"type": "string", "description": "Sticker file ID or emoji description"},
            },
            "required": ["sticker"],
        },
        handler=lambda ctx: telegram.send_message(
            chat_id=0,  # will be replaced with current chat
            text=f"[Sticker: {ctx.args['sticker']}]",
        ),
    ))

    tools.append(Tool(
        name="sticker_list",
        description="List your favorite stickers.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=lambda ctx: "You have no saved stickers yet.",
    ))

    tools.append(Tool(
        name="sticker_save",
        description="Save a sticker to your favorites.",
        parameters={
            "type": "object",
            "properties": {
                "sticker_id": {"type": "string", "description": "The sticker file ID to save"},
            },
            "required": ["sticker_id"],
        },
        handler=lambda ctx: f"Sticker {ctx.args['sticker_id']} saved.",
    ))

    return tools


def create_take_photo_tool() -> Tool:
    """Generate an image using Stable Diffusion."""
    return Tool(
        name="take_photo",
        description="Generate a photo/image using AI (Stable Diffusion).",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The image description/prompt"},
                "negative_prompt": {"type": "string", "description": "What to avoid in the image", "default": ""},
                "width": {"type": "integer", "description": "Image width", "default": 512},
                "height": {"type": "integer", "description": "Image height", "default": 512},
            },
            "required": ["prompt"],
        },
        handler=lambda ctx: f"[Image generated: {ctx.args['prompt']}] (mock)",
    )


def create_record_audio_tool() -> Tool:
    """Generate a voice message using TTS."""
    return Tool(
        name="record_audio",
        description="Record and send a voice message (text-to-speech).",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to speak"},
                "voice": {"type": "string", "description": "Voice name or ID (optional)"},
            },
            "required": ["text"],
        },
        handler=lambda ctx: f"[Voice message: {ctx.args['text']}] (mock)",
    )


def create_react_with_emoji_tool(
    telegram: TelegramClient,
) -> Tool:
    """React to a message with an emoji."""
    return Tool(
        name="react_with_emoji",
        description="React to a message with an emoji.",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Chat ID"},
                "message_id": {"type": "integer", "description": "Message ID"},
                "emoji": {"type": "string", "description": "Emoji to react with (e.g., 👍, ❤️, 😂)"},
            },
            "required": ["chat_id", "message_id", "emoji"],
        },
        handler=lambda ctx: telegram.react_with_emoji(
            ctx.args["chat_id"],
            ctx.args["message_id"],
            ctx.args["emoji"],
        ),
    )


def create_forward_message_tool(
    telegram: TelegramClient,
) -> Tool:
    """Forward a message to another chat."""
    return Tool(
        name="forward_message",
        description="Forward a message from one chat to another.",
        parameters={
            "type": "object",
            "properties": {
                "from_chat_id": {"type": "integer", "description": "Source chat ID"},
                "message_id": {"type": "integer", "description": "Message ID to forward"},
                "to_chat_id": {"type": "integer", "description": "Destination chat ID"},
            },
            "required": ["from_chat_id", "message_id", "to_chat_id"],
        },
        handler=lambda ctx: telegram.forward_message(
            ctx.args["from_chat_id"],
            ctx.args["message_id"],
            ctx.args["to_chat_id"],
        ),
    )


def create_edit_message_tool(
    telegram: TelegramClient,
) -> Tool:
    """Edit a message's text."""
    return Tool(
        name="edit_message_text",
        description="Edit the text of a sent message.",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Chat ID"},
                "message_id": {"type": "integer", "description": "Message ID to edit"},
                "new_text": {"type": "string", "description": "New message text"},
            },
            "required": ["chat_id", "message_id", "new_text"],
        },
        handler=lambda ctx: telegram.edit_message_text(
            ctx.args["chat_id"],
            ctx.args["message_id"],
            ctx.args["new_text"],
        ),
    )


def create_remove_message_tool(
    telegram: TelegramClient,
) -> Tool:
    """Delete a message."""
    return Tool(
        name="remove_message",
        description="Delete a message (only allowed for own messages or if admin).",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Chat ID"},
                "message_id": {"type": "integer", "description": "Message ID to delete"},
            },
            "required": ["chat_id", "message_id"],
        },
        handler=lambda ctx: telegram.delete_message(
            ctx.args["chat_id"],
            ctx.args["message_id"],
        ),
    )


def create_group_admin_tools(
    telegram: TelegramClient,
) -> List[Tool]:
    """Create group admin tools."""
    tools = []

    tools.append(Tool(
        name="group_admin_ban_user",
        description="Ban a user from a group (admin only).",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Group chat ID"},
                "user_id": {"type": "integer", "description": "User ID to ban"},
            },
            "required": ["chat_id", "user_id"],
        },
        handler=lambda ctx: f"Banned user {ctx.args['user_id']} from chat {ctx.args['chat_id']} (mock)",
    ))

    tools.append(Tool(
        name="group_admin_remove_message",
        description="Remove a message from a group (admin only).",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Group chat ID"},
                "message_id": {"type": "integer", "description": "Message ID to remove"},
            },
            "required": ["chat_id", "message_id"],
        },
        handler=lambda ctx: f"Removed message {ctx.args['message_id']} from chat {ctx.args['chat_id']} (mock)",
    ))

    tools.append(Tool(
        name="group_admin_set_user_tag",
        description="Set a tag/role for a user in a group (admin only).",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Group chat ID"},
                "user_id": {"type": "integer", "description": "User ID"},
                "tag": {"type": "string", "description": "Tag to assign (e.g., 'member', 'moderator', 'admin')"},
            },
            "required": ["chat_id", "user_id", "tag"],
        },
        handler=lambda ctx: f"Set tag {ctx.args['tag']} for user {ctx.args['user_id']} in chat {ctx.args['chat_id']} (mock)",
    ))

    return tools


def create_web_search_tool() -> Tool:
    """Web search tool (requires API key)."""
    return Tool(
        name="web_search",
        description=" the web for current information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
            },
            "required": ["query"],
        },
        handler=lambda ctx: f"[Web search results for: {ctx.args['query']}] (mock)",
    )


# ============================================================
# Helper to build default tools
# ============================================================

def create_default_tools(
    telegram: TelegramClient,
    diary: Diary,
    openai: OpenAIChat,
    current_chat: Optional[TelegramChat] = None,
    is_admin: bool = False,
) -> OpenAITools:
    """Create a standard set of tools for the LLM."""
    tools = OpenAITools()

    # Core tools
    tools.insert(create_send_telegram_message_tool(telegram, current_chat))
    tools.insert(create_get_telegram_chats_tool(telegram))
    tools.insert(create_search_chats_tool(telegram))
    tools.insert(create_search_messages_tool(telegram))
    tools.insert(create_open_chat_tool(telegram))
    tools.insert(create_ask_tool(diary, openai))

    # Media tools
    if get_config().capability_take_photo:
        tools.insert(create_take_photo_tool())

    if get_config().capability_record_voice:
        tools.insert(create_record_audio_tool())

    # Sticker tools
    if get_config().capability_use_stickers:
        for st in create_sticker_tools(telegram):
            tools.insert(st)

    # Interaction tools
    tools.insert(create_react_with_emoji_tool(telegram))
    tools.insert(create_forward_message_tool(telegram))
    tools.insert(create_edit_message_tool(telegram))
    tools.insert(create_remove_message_tool(telegram))

    # Admin tools
    if is_admin:
        for at in create_group_admin_tools(telegram):
            tools.insert(at)

    # Web search
    if get_config().capability_web_search:
        tools.insert(create_web_search_tool())

    return tools
