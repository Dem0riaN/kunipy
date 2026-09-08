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
import difflib
import json
import logging
import random
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import aiohttp

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
    recent_bot_messages: Optional[List[str]] = None,
) -> Tool:
    """Send a message to a Telegram chat."""

    async def _handle(ctx: ToolContext) -> Any:
        text = ctx.args["text"]
        current_chat_id = chat.id if chat else 0
        requested_chat_id = ctx.args.get("chat_id")

        # Guard against the model confusing chats: reject any explicit
        # chat_id that doesn't match the chat this tool instance was bound
        # to, instead of silently sending there.
        if requested_chat_id and current_chat_id and requested_chat_id != current_chat_id:
            title = chat.title if chat else str(current_chat_id)
            return (
                f'Error: you can\'t send messages to other chats. Open them first. '
                f'You are currently in chat "{title}" (chat_id={current_chat_id}).'
            )
        chat_id = requested_chat_id or current_chat_id

        reply_to = ctx.args.get("reply_to")
        if reply_to and chat_id:
            # Guard against replying to a message_id that belongs to a
            # different chat (a real, previously-observed failure mode: the
            # model mixes up message IDs across chats it has open).
            recent_history = await telegram.get_chat_history(chat_id, limit=30)
            if not any(m.id == reply_to for m in recent_history):
                return (
                    "Error: you are trying to reply to a message that isn't in this chat's recent "
                    "history. Don't guess message IDs -- only reply_to a message_id you actually saw "
                    "in this conversation, or omit reply_to."
                )

        repeat_warning = _check_anti_repeat(text, recent_bot_messages)
        if repeat_warning:
            return repeat_warning

        await _simulate_typing(telegram, chat_id, text)
        return await telegram.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to,
        )

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
        handler=_handle,
    )


def _check_anti_repeat(text: str, recent_bot_messages: Optional[List[str]]) -> Optional[str]:
    """Compare `text` against the bot's own recent messages in this chat and
    return a rejection message (instead of sending) if it looks like a
    near-duplicate of something already said.

    Uses plain text similarity (difflib) rather than embeddings, trading a
    bit of semantic precision for zero extra network round-trips on every
    single message send.
    """
    if not recent_bot_messages or not text.strip():
        return None

    config = get_config()
    history = recent_bot_messages[-config.anti_repeat_max_history:]
    if not history:
        return None

    ratios = [difflib.SequenceMatcher(None, text, past).ratio() for past in history if past.strip()]
    if not ratios:
        return None

    max_ratio = max(ratios)
    avg_ratio = sum(ratios) / len(ratios)

    if max_ratio >= config.anti_repeat_trigger_max or avg_ratio >= config.anti_repeat_trigger_avg:
        return (
            "Error: this message is too similar to something you already said recently in this chat "
            f"(similarity={max_ratio:.2f}). Say something meaningfully different, or don't send anything."
        )
    return None


async def _simulate_typing(telegram: TelegramClient, chat_id: int, text: str) -> None:
    """Show a "typing..." indicator for a duration proportional to the
    message length, so replies don't appear unnaturally instantly."""
    if not chat_id or not text:
        return
    config = get_config()
    min_wpm = max(config.typing_simulation_min_wpm, 1)
    max_wpm = max(config.typing_simulation_max_wpm, min_wpm)
    wpm = random.uniform(min_wpm, max_wpm)

    word_count = max(len(text.split()), 1)
    duration = min((word_count / wpm) * 60.0, 8.0)  # cap so long replies don't stall the chat forever

    try:
        await telegram.send_typing(chat_id)
        if duration > 0.1:
            await asyncio.sleep(duration)
    except Exception as e:
        logger.debug(f"Typing simulation failed (non-fatal): {e}")


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
    """Search chats by name."""
    return Tool(
        name="search_chats",
        description="Search for chats by name or title.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
            },
            "required": ["query"],
        },
        handler=lambda ctx: telegram.search_chats(ctx.args["query"]),
    )


def create_search_messages_tool(
    telegram: TelegramClient,
) -> Tool:
    """Search messages in a chat."""
    return Tool(
        name="search_messages",
        description="Search for messages in a specific chat or globally.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
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
    chat: Optional[TelegramChat] = None,
) -> List[Tool]:
    """Create sticker-related tools."""
    tools = []

    async def _sticker_send(ctx: ToolContext) -> str:
        chat_id = ctx.args.get("chat_id") or (chat.id if chat else 0)
        if not chat_id:
            return "Error: no chat_id available to send the sticker to."
        await telegram.send_sticker(chat_id, ctx.args["sticker"])
        return f"Sticker {ctx.args['sticker']} sent."

    tools.append(Tool(
        name="sticker_send",
        description="Send a sticker (by its Telegram file_id) to the current chat.",
        parameters={
            "type": "object",
            "properties": {
                "sticker": {"type": "string", "description": "Sticker file_id (see sticker_list)"},
                "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
            },
            "required": ["sticker"],
        },
        handler=_sticker_send,
    ))

    async def _sticker_list(ctx: ToolContext) -> str:
        stickers = await telegram.get_stickers(limit=ctx.args.get("limit", 20))
        if not stickers:
            return "You have no saved stickers yet."
        lines = [f"{s['emoji'] or '?'} -> file_id={s['file_id']}" for s in stickers if s.get("file_id")]
        return "Your stickers:\n" + "\n".join(lines) if lines else "You have no saved stickers yet."

    tools.append(Tool(
        name="sticker_list",
        description="List your favorite/recently used stickers.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of stickers to list", "default": 20},
            },
        },
        handler=_sticker_list,
    ))

    async def _sticker_save(ctx: ToolContext) -> str:
        ok = await telegram.save_sticker(ctx.args["sticker_id"])
        return f"Sticker {ctx.args['sticker_id']} saved." if ok else f"Failed to save sticker {ctx.args['sticker_id']}."

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
        handler=_sticker_save,
    ))

    return tools


def create_take_photo_tool(
    telegram: TelegramClient,
    chat: Optional[TelegramChat] = None,
) -> Tool:
    """Generate an image using Stable Diffusion and send it to the chat."""

    async def _handle(ctx: ToolContext) -> str:
        from .image_generator import get_image_generator

        chat_id = ctx.args.get("chat_id") or (chat.id if chat else 0)
        generator = get_image_generator()
        path = await generator.generate_and_save(
            prompt=ctx.args["prompt"],
            negative_prompt=ctx.args.get("negative_prompt", ""),
            width=ctx.args.get("width", 512),
            height=ctx.args.get("height", 512),
        )
        if not path:
            return "Error: image generation failed or is disabled."
        if chat_id:
            await telegram.send_photo(chat_id, path, caption=ctx.args["prompt"][:1000])
            return f"Photo generated and sent ({path})."
        return f"Photo generated at {path} (no chat to send to)."

    return Tool(
        name="take_photo",
        description="Generate a photo/image using AI (Stable Diffusion) and send it to the chat.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The image description/prompt"},
                "negative_prompt": {"type": "string", "description": "What to avoid in the image", "default": ""},
                "width": {"type": "integer", "description": "Image width", "default": 512},
                "height": {"type": "integer", "description": "Image height", "default": 512},
                "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
            },
            "required": ["prompt"],
        },
        handler=_handle,
    )


def create_record_audio_tool(
    telegram: TelegramClient,
    openai: OpenAIChat,
    chat: Optional[TelegramChat] = None,
) -> Tool:
    """Generate a voice message using TTS and send it to the chat."""

    async def _handle(ctx: ToolContext) -> str:
        import time
        from pathlib import Path

        chat_id = ctx.args.get("chat_id") or (chat.id if chat else 0)
        audio = await openai.synthesize_speech(ctx.args["text"], voice=ctx.args.get("voice"))
        if not audio:
            return "Error: text-to-speech failed or is disabled."

        config = get_config()
        ext = "mp3" if config.record_voice_backend.value == "elevenlabs" else config.record_voice_openai_format
        out_dir = Path("data/generated_audio")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{int(time.time() * 1000)}.{ext}"
        path.write_bytes(audio)

        if chat_id:
            await telegram.send_voice(chat_id, str(path), caption=ctx.args["text"][:200])
            return f"Voice message generated and sent ({path})."
        return f"Voice message generated at {path} (no chat to send to)."

    return Tool(
        name="record_audio",
        description="Record and send a voice message (text-to-speech).",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to speak"},
                "voice": {"type": "string", "description": "Voice name or ID (optional)"},
                "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
            },
            "required": ["text"],
        },
        handler=_handle,
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

    async def _ban_user(ctx: ToolContext) -> str:
        ok = await telegram.ban_chat_member(ctx.args["chat_id"], ctx.args["user_id"])
        if ok:
            return f"Banned user {ctx.args['user_id']} from chat {ctx.args['chat_id']}."
        return f"Error: failed to ban user {ctx.args['user_id']} (missing rights or invalid IDs)."

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
        handler=_ban_user,
    ))

    async def _remove_message(ctx: ToolContext) -> str:
        await telegram.delete_message(ctx.args["chat_id"], ctx.args["message_id"])
        return f"Removed message {ctx.args['message_id']} from chat {ctx.args['chat_id']}."

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
        handler=_remove_message,
    ))

    async def _set_user_tag(ctx: ToolContext) -> str:
        ok = await telegram.set_member_tag(ctx.args["chat_id"], ctx.args["user_id"], ctx.args["tag"])
        if ok:
            return f"Set tag '{ctx.args['tag']}' for user {ctx.args['user_id']} in chat {ctx.args['chat_id']}."
        return f"Error: failed to set tag for user {ctx.args['user_id']} (missing rights or invalid IDs)."

    tools.append(Tool(
        name="group_admin_set_user_tag",
        description=(
            "Set a role for a user in a group (admin only). "
            "tag='admin' or 'moderator' promotes to administrator; any other value demotes to a plain member."
        ),
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "Group chat ID"},
                "user_id": {"type": "integer", "description": "User ID"},
                "tag": {"type": "string", "description": "Tag to assign (e.g., 'member', 'moderator', 'admin')"},
            },
            "required": ["chat_id", "user_id", "tag"],
        },
        handler=_set_user_tag,
    ))

    return tools


def create_web_search_tool() -> Tool:
    """Web search tool, backed by Ollama's cloud web search API.

    Requires `capabilities.web_search.ollama_bearer_key` to be set in
    config.toml (get a free key at https://ollama.com). Without it, the tool
    still works but is subject to a much stricter anonymous rate limit.
    """

    async def _handle(ctx: ToolContext) -> str:
        config = get_config()
        query = ctx.args["query"]
        max_results = ctx.args.get("max_results", 5)

        headers = {"Content-Type": "application/json"}
        if config.web_search_ollama_key:
            headers["Authorization"] = f"Bearer {config.web_search_ollama_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://ollama.com/api/web_search",
                    json={"query": query, "max_results": max_results},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        return f"Error: web search failed ({resp.status}): {err[:300]}"
                    data = await resp.json()
        except Exception as e:
            return f"Error: web search request failed: {e}"

        results = data.get("results", [])
        if not results:
            return f"No web search results found for: {query}"

        parts = [f"Web search results for: {query}\n"]
        for r in results[:max_results]:
            title = r.get("title", "")
            url = r.get("url", "")
            content = (r.get("content") or "")[:400]
            parts.append(f"- {title} ({url})\n  {content}")
        return "\n".join(parts)

    return Tool(
        name="web_search",
        description="Search the web for current information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
            },
            "required": ["query"],
        },
        handler=_handle,
    )


# ============================================================
# Helper to build default tools
# ============================================================

def create_join_chat_tool(telegram: TelegramClient) -> Tool:
    """Join a chat/channel by invite link."""

    async def _handle(ctx: ToolContext) -> str:
        try:
            chat_id = await telegram.join_chat_by_link(ctx.args["invite_link"])
            return f"Joined chat, chat_id={chat_id}."
        except RuntimeError as e:
            return f"Error: {e}"

    return Tool(
        name="join_chat",
        description="Join a chat, group, or channel using an invite link (t.me/... or +invite hash).",
        parameters={
            "type": "object",
            "properties": {
                "invite_link": {"type": "string", "description": "The invite link to join"},
            },
            "required": ["invite_link"],
        },
        handler=_handle,
    )


def create_leave_chat_tool(telegram: TelegramClient) -> Tool:
    """Leave a chat/group/channel."""

    async def _handle(ctx: ToolContext) -> str:
        await telegram.leave_chat(ctx.args["chat_id"])
        return f"Left chat {ctx.args['chat_id']}."

    return Tool(
        name="leave_chat",
        description="Leave a chat, group, or channel.",
        parameters={
            "type": "object",
            "properties": {
                "chat_id": {"type": "integer", "description": "The chat ID to leave"},
            },
            "required": ["chat_id"],
        },
        handler=_handle,
    )


def create_default_tools(
    telegram: TelegramClient,
    diary: Diary,
    openai: OpenAIChat,
    current_chat: Optional[TelegramChat] = None,
    is_admin: bool = False,
    recent_bot_messages: Optional[List[str]] = None,
) -> OpenAITools:
    """Create a standard set of tools for the LLM."""
    tools = OpenAITools()

    # Core tools
    tools.insert(create_send_telegram_message_tool(telegram, current_chat, recent_bot_messages))
    tools.insert(create_get_telegram_chats_tool(telegram))
    tools.insert(create_search_chats_tool(telegram))
    tools.insert(create_search_messages_tool(telegram))
    tools.insert(create_open_chat_tool(telegram))
    tools.insert(create_ask_tool(diary, openai))

    # Media tools
    if get_config().capability_take_photo:
        tools.insert(create_take_photo_tool(telegram, current_chat))

    if get_config().capability_record_voice:
        tools.insert(create_record_audio_tool(telegram, openai, current_chat))

    # Sticker tools
    if get_config().capability_use_stickers:
        for st in create_sticker_tools(telegram, current_chat):
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

    # Chat membership tools
    if get_config().can_join_chats:
        tools.insert(create_join_chat_tool(telegram))
    if get_config().can_leave_chats:
        tools.insert(create_leave_chat_tool(telegram))

    return tools
