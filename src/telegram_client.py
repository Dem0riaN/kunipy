"""Telegram client for kunipy using aiotdlib (TDLib).

Provides async wrapper around TDLib for message handling, chat management,
and event streaming with full userbot capabilities.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

from aiotdlib import Client, TDLibError
from aiotdlib.api import (
    Chat,
    ChatType,
    Message,
    MessageSender,
    MessageSenderUser,
    Update,
    UpdateNewMessage,
    UpdateChat,
    UpdateUser,
)

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    """A Telegram message (simplified for internal use)."""
    id: int
    chat_id: int
    sender_id: int
    date: int  # Unix timestamp
    content: str  # text content
    is_outgoing: bool = False
    reply_to_message_id: Optional[int] = None
    media: Optional[Dict[str, Any]] = None


@dataclass
class TelegramChat:
    """A Telegram chat (simplified)."""
    id: int
    title: str
    type: str  # "private", "group", "supergroup", "channel"
    unread_count: int = 0
    is_pinned: bool = False
    is_member: bool = True
    last_message: Optional[TelegramMessage] = None


@dataclass
class TelegramUser:
    """A Telegram user."""
    id: int
    first_name: str
    last_name: str = ""
    username: str = ""
    phone_number: str = ""


class TelegramClient:
    """Async Telegram client using aiotdlib.

    Manages TDLib connection, authentication, and provides high-level methods
    for interacting with Telegram.
    """

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        database_dir: str = "data/tdlib",
        files_dir: str = "data/tdlib_files",
    ):
        config = get_config()
        self.api_id = api_id or config.telegram_api_id
        self.api_hash = api_hash or config.telegram_api_hash
        self.database_dir = Path(database_dir)
        self.files_dir = Path(files_dir)
        self._client: Optional[Client] = None
        self._my_id: Optional[int] = None
        self._is_ready = False
        self._chat_cache: Dict[int, TelegramChat] = {}
        self._user_cache: Dict[int, TelegramUser] = {}
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._loop_task: Optional[asyncio.Task] = None

    async def start(self, phone_number: Optional[str] = None) -> None:
        """Initialize connection to Telegram and authenticate."""
        if not self.api_id or not self.api_hash:
            raise ValueError("Telegram API ID and hash must be set in config.toml")

        self.database_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

        # Create client
        self._client = Client(
            api_id=self.api_id,
            api_hash=self.api_hash,
            database_directory=str(self.database_dir),
            files_directory=str(self.files_dir),
            use_test_dc=False,
        )

        # Register update handlers
        self._client.add_update_handler(self._handle_update)

        # If phone number not passed, try config
        if phone_number is None:
            config = get_config()
            phone_number = config.telegram_phone or None

        # Define code request handler
        async def on_code(phone: str, code_type: str) -> str:
            logger.info(f"Code requested for {phone}, type: {code_type}")
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, input, f"Enter code for {phone}: ")

        # Start the client (this connects and authenticates)
        logger.info("Starting Telegram client and authenticating...")
        try:
            await self._client.start(
                phone_number=phone_number,
                on_code=on_code,
            )
            # Get my user info
            me = await self._client.get_me()
            self._my_id = me.id
            self._is_ready = True
            logger.info(f"Logged in as {me.first_name} (ID: {self._my_id})")
        except Exception as e:
            logger.error(f"Failed to start Telegram client: {e}")
            raise

    async def stop(self) -> None:
        """Shutdown Telegram client."""
        self._is_ready = False
        if self._client:
            await self._client.close()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

    async def wait_for_connection(self) -> None:
        """Wait until the client is connected and ready."""
        while not self._is_ready:
            await asyncio.sleep(0.1)

    @property
    def my_id(self) -> Optional[int]:
        return self._my_id

    # ---------- High-level methods ----------

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int] = None,
        parse_mode: str = "HTML",
    ) -> TelegramMessage:
        """Send a text message to a chat."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        # Convert parse_mode to TDLib format
        input_text = self._client.api.input_message_text(
            text=text,
            parse_mode=self._client.api.parse_mode_html() if parse_mode == "HTML" else None,
        )
        reply_to = self._client.api.message_send_options(
            reply_to_message_id=reply_to_message_id,
        ) if reply_to_message_id else None

        try:
            msg = await self._client.send_message(
                chat_id=chat_id,
                reply_to=reply_to,
                input_message_content=input_text,
            )
            return self._convert_message(msg)
        except TDLibError as e:
            logger.error(f"Failed to send message: {e}")
            raise RuntimeError(f"Telegram error: {e}")

    async def get_chat(self, chat_id: int) -> Optional[TelegramChat]:
        """Get chat by ID."""
        if not self._client:
            return None
        if chat_id in self._chat_cache:
            return self._chat_cache[chat_id]
        try:
            chat = await self._client.get_chat(chat_id=chat_id)
            tc = self._convert_chat(chat)
            self._chat_cache[chat_id] = tc
            return tc
        except TDLibError:
            return None

    async def get_user(self, user_id: int) -> Optional[TelegramUser]:
        """Get user by ID."""
        if not self._client:
            return None
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            user = await self._client.get_user(user_id=user_id)
            tu = self._convert_user(user)
            self._user_cache[user_id] = tu
            return tu
        except TDLibError:
            return None

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 30,
        from_message_id: int = 0,
    ) -> List[TelegramMessage]:
        """Get chat message history."""
        if not self._client:
            return []
        try:
            # Use get_chat_history
            messages = await self._client.get_chat_history(
                chat_id=chat_id,
                from_message_id=from_message_id,
                offset=0,
                limit=limit,
                only_local=False,
            )
            return [self._convert_message(m) for m in messages]
        except TDLibError as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

    async def open_chat(self, chat_id: int) -> None:
        """Open a chat (mark as read)."""
        if not self._client:
            return
        try:
            await self._client.open_chat(chat_id=chat_id)
        except TDLibError as e:
            logger.error(f"Failed to open chat: {e}")

    async def close_chat(self, chat_id: int) -> None:
        """Close a chat."""
        if not self._client:
            return
        try:
            await self._client.close_chat(chat_id=chat_id)
        except TDLibError as e:
            logger.error(f"Failed to close chat: {e}")

    async def view_messages(self, chat_id: int, message_ids: List[int]) -> None:
        """Mark messages as viewed."""
        if not self._client:
            return
        try:
            await self._client.view_messages(
                chat_id=chat_id,
                message_ids=message_ids,
                source=None,
            )
        except TDLibError as e:
            logger.error(f"Failed to view messages: {e}")

    async def react_with_emoji(self, chat_id: int, message_id: int, emoji: str) -> None:
        """React to a message with an emoji."""
        if not self._client:
            return
        try:
            await self._client.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=self._client.api.reaction_type_emoji(emoji=emoji),
                is_big=False,
            )
        except TDLibError as e:
            logger.error(f"Failed to react: {e}")

    async def forward_message(
        self,
        from_chat_id: int,
        message_id: int,
        to_chat_id: int,
    ) -> None:
        """Forward a message to another chat."""
        if not self._client:
            return
        try:
            await self._client.forward_messages(
                chat_id=to_chat_id,
                from_chat_id=from_chat_id,
                message_ids=[message_id],
                options=None,
            )
        except TDLibError as e:
            logger.error(f"Failed to forward message: {e}")

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        new_text: str,
    ) -> None:
        """Edit a message text."""
        if not self._client:
            return
        try:
            input_text = self._client.api.input_message_text(
                text=new_text,
                parse_mode=self._client.api.parse_mode_html(),
            )
            await self._client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                input_message_content=input_text,
            )
        except TDLibError as e:
            logger.error(f"Failed to edit message: {e}")

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        """Delete a message."""
        if not self._client:
            return
        try:
            await self._client.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id],
                revoke=True,
            )
        except TDLibError as e:
            logger.error(f"Failed to delete message: {e}")

    async def join_chat_by_link(self, invite_link: str) -> int:
        """Join a chat by invite link. Returns chat ID."""
        if not self._client:
            raise RuntimeError("Client not initialized")
        try:
            chat = await self._client.join_chat_by_invite_link(invite_link=invite_link)
            return chat.id
        except TDLibError as e:
            logger.error(f"Failed to join chat: {e}")
            raise RuntimeError(f"Failed to join: {e}")

    async def leave_chat(self, chat_id: int) -> None:
        """Leave a chat."""
        if not self._client:
            return
        try:
            await self._client.leave_chat(chat_id=chat_id)
        except TDLibError as e:
            logger.error(f"Failed to leave chat: {e}")

    async def search_chats(self, query: str) -> List[TelegramChat]:
        """ chats by name."""
        if not self._client:
            return []
        try:
            result = await self._client.search_chats(
                query=query,
                limit=20,
            )
            chats = []
            for chat_id in result.chat_ids:
                chat = await self.get_chat(chat_id)
                if chat:
                    chats.append(chat)
            return chats
        except TDLibError as e:
            logger.error(f"Failed to search chats: {e}")
            return []

    async def search_messages(
        self,
        chat_id: Optional[int] = None,
        query: str = "",
        limit: int = 10,
    ) -> List[TelegramMessage]:
        """ messages in a chat or globally."""
        if not self._client:
            return []
        try:
            # Use search_messages
            result = await self._client.search_messages(
                chat_list=None,  # All chats
                query=query,
                offset=0,
                limit=limit,
                filter=None,
                message_thread_id=0,
            ) if chat_id is None else await self._client.search_messages(
                chat_list=self._client.api.chat_list_main(),  # Actually we need to filter by chat_id manually
                query=query,
                offset=0,
                limit=limit,
                filter=None,
                message_thread_id=0,
            )
            # Need to filter by chat_id if provided
            messages = []
            for msg in result.messages:
                if chat_id is not None and msg.chat_id != chat_id:
                    continue
                messages.append(self._convert_message(msg))
            return messages
        except TDLibError as e:
            logger.error(f"Failed to search messages: {e}")
            return []

    async def get_chats(self, limit: int = 200) -> List[TelegramChat]:
        """Get all chats."""
        if not self._client:
            return []
        try:
            result = await self._client.get_chats(
                chat_list=self._client.api.chat_list_main(),
                limit=limit,
            )
            chats = []
            for chat_id in result.chat_ids:
                chat = await self.get_chat(chat_id)
                if chat:
                    chats.append(chat)
            return chats
        except TDLibError as e:
            logger.error(f"Failed to get chats: {e}")
            return []

    # ---------- Event handling ----------

    def add_event_handler(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for incoming events."""
        self._callbacks.append(callback)

    async def _handle_update(self, update: Update) -> None:
        """Handle TDLib updates and emit events."""
        # Convert to dict for compatibility
        event = self._convert_update(update)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

    def _convert_update(self, update: Update) -> Dict[str, Any]:
        """Convert a TDLib update to a dict."""
        if isinstance(update, UpdateNewMessage):
            msg = self._convert_message(update.message)
            return {
                "type": "updateNewMessage",
                "message": msg,
                "chat_id": msg.chat_id,
            }
        elif isinstance(update, UpdateChat):
            return {
                "type": "updateChat",
                "chat_id": update.chat.id,
                "chat": self._convert_chat(update.chat),
            }
        elif isinstance(update, UpdateUser):
            return {
                "type": "updateUser",
                "user": self._convert_user(update.user),
            }
        else:
            return {
                "type": "unknown",
                "update": str(update),
            }

    # ---------- Conversion helpers ----------

    def _convert_message(self, msg: Message) -> TelegramMessage:
        """Convert TDLib Message to internal TelegramMessage."""
        # Extract text
        content = ""
        if msg.content:
            if hasattr(msg.content, "text"):
                content = msg.content.text or ""
            elif hasattr(msg.content, "caption"):
                content = msg.content.caption or ""
        # Determine sender
        sender_id = 0
        if msg.sender_id:
            if isinstance(msg.sender_id, MessageSenderUser):
                sender_id = msg.sender_id.user_id
        is_outgoing = (sender_id == self._my_id)
        return TelegramMessage(
            id=msg.id,
            chat_id=msg.chat_id,
            sender_id=sender_id,
            date=msg.date,
            content=content,
            is_outgoing=is_outgoing,
            reply_to_message_id=msg.reply_to_message_id,
            media=None,  # simplified
        )

    def _convert_chat(self, chat: Chat) -> TelegramChat:
        """Convert TDLib Chat to internal TelegramChat."""
        # Determine type
        chat_type = "private"
        if chat.type:
            if hasattr(chat.type, "class_name"):
                class_name = chat.type.class_name
                if class_name == "chatTypePrivate":
                    chat_type = "private"
                elif class_name == "chatTypeBasicGroup":
                    chat_type = "group"
                elif class_name == "chatTypeSupergroup":
                    # Check if channel
                    if hasattr(chat.type, "is_channel") and chat.type.is_channel:
                        chat_type = "channel"
                    else:
                        chat_type = "supergroup"
        # Check pinned
        is_pinned = False
        if chat.positions:
            for pos in chat.positions:
                if pos.is_pinned:
                    is_pinned = True
                    break
        return TelegramChat(
            id=chat.id,
            title=chat.title or "",
            type=chat_type,
            unread_count=chat.unread_count or 0,
            is_pinned=is_pinned,
            is_member=True,  # we'll check membership later
            last_message=self._convert_message(chat.last_message) if chat.last_message else None,
        )

    def _convert_user(self, user) -> TelegramUser:
        """Convert TDLib User to internal TelegramUser."""
        return TelegramUser(
            id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username or "",
            phone_number=user.phone_number or "",
        )

    # ---------- Additional features ----------

    async def send_typing(self, chat_id: int) -> None:
        """Send typing action."""
        if not self._client:
            return
        try:
            await self._client.send_chat_action(
                chat_id=chat_id,
                action=self._client.api.chat_action_typing(),
            )
        except TDLibError as e:
            logger.debug(f"Failed to send typing: {e}")

    async def send_sticker(self, chat_id: int, sticker_file_id: str) -> None:
        """Send a sticker by file ID."""
        if not self._client:
            return
        try:
            # Get sticker file
            file = await self._client.get_file(file_id=sticker_file_id)
            input_file = self._client.api.input_file_id(id=file.id)
            sticker_input = self._client.api.input_message_sticker(
                sticker=input_file,
                width=512,
                height=512,
                emoji=None,
            )
            await self._client.send_message(
                chat_id=chat_id,
                input_message_content=sticker_input,
            )
        except TDLibError as e:
            logger.error(f"Failed to send sticker: {e}")

    async def get_stickers(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get favorite stickers."""
        if not self._client:
            return []
        try:
            stickers = await self._client.get_stickers(
                sticker_type=self._client.api.sticker_type_regular(),
                limit=limit,
            )
            return [
                {
                    "id": s.id,
                    "emoji": s.emoji,
                    "file_id": s.sticker.file.id if s.sticker and s.sticker.file else None,
                }
                for s in stickers.stickers
            ]
        except TDLibError as e:
            logger.error(f"Failed to get stickers: {e}")
            return []

    async def save_sticker(self, sticker_file_id: str) -> bool:
        """Save a sticker to favorites."""
        if not self._client:
            return False
        try:
            # Get sticker
            sticker = await self._client.get_sticker(file_id=sticker_file_id)
            await self._client.add_sticker_to_set(
                sticker_set_name=None,  # add to favorite
                sticker=sticker,
            )
            return True
        except TDLibError as e:
            logger.error(f"Failed to save sticker: {e}")
            return False


# Singleton instance
_client: Optional[TelegramClient] = None


def get_telegram_client() -> TelegramClient:
    """Get global Telegram client instance."""
    global _client
    if _client is None:
        _client = TelegramClient()
    return _client
