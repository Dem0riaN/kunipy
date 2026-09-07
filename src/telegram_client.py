"""Telegram client for kunipy using aiotdlib (TDLib).

Provides async wrapper around TDLib for message handling, chat management,
and event streaming with full userbot capabilities.

IMPORTANT: this module talks to the *real* aiotdlib public API (verified against
aiotdlib's installed source, since large parts of its public surface are
convenience methods on `aiotdlib.Client`, not on `Client.api`). Concretely:

- Client is constructed from a single `ClientSettings` object.
- Phone-number / 2FA / registration interactive login is handled internally
  by aiotdlib (`Client.start()` -> `Client.authorize()`), no manual callback
  is needed or possible.
- High level actions (send_text, send_photo, send_voice_note, send_sticker,
  forward_messages, edit_text, get_chat, get_user, get_main_list_chats,
  iter_chat_history) are methods on `Client` itself.
- Anything without a `Client` convenience wrapper is called through
  `Client.api.<tdlib_function_name>(...)`, using the *real* TDLib function
  names (e.g. `open_chat`, `close_chat`, `view_messages`,
  `add_message_reaction`, `search_chats`, `search_chat_messages`,
  `get_stickers`, `add_favorite_sticker`, `send_chat_action`, `get_file`).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aiotdlib import Client, ClientSettings
from aiotdlib.api.errors.error import AioTDLibError
from aiotdlib.api import types as td

from .config import get_config

logger = logging.getLogger(__name__)

# Alias kept for callers that want to catch Telegram-specific errors.
TDLibError = AioTDLibError


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
        # aiotdlib only exposes a single `files_directory`; TDLib keeps its
        # own database files alongside the downloaded files under that path.
        self.files_dir = Path(database_dir if database_dir else files_dir)
        self._client: Optional[Client] = None
        self._my_id: Optional[int] = None
        self._is_ready = False
        self._chat_cache: Dict[int, TelegramChat] = {}
        self._user_cache: Dict[int, TelegramUser] = {}
        self._callbacks: List[Callable[[Dict[str, Any]], Any]] = []

    async def start(self, phone_number: Optional[str] = None) -> None:
        """Initialize connection to Telegram and authenticate.

        Phone number / SMS-code / 2FA-password / registration prompts are all
        handled interactively by aiotdlib itself (it reads from stdin), so we
        just need to provide the phone number (if we have one) and wait.
        """
        if not self.api_id or not self.api_hash:
            raise ValueError("Telegram API ID and hash must be set in config.toml")

        self.files_dir.mkdir(parents=True, exist_ok=True)

        if phone_number is None:
            config = get_config()
            phone_number = getattr(config, "telegram_phone", "") or None

        settings = ClientSettings(
            api_id=self.api_id,
            api_hash=self.api_hash,
            phone_number=phone_number,
            files_directory=self.files_dir,
            device_model="kunipy",
            application_version="0.1.0",
        )
        self._client = Client(settings=settings)

        # Register a single catch-all handler; we dispatch by update type.
        self._client.add_event_handler(self._handle_update, td.API.Types.ANY)

        logger.info("Starting Telegram client and authenticating...")
        try:
            await self._client.start()
            self._my_id = await self._client.get_my_id()
            self._is_ready = True
            logger.info(f"Logged in, my_id={self._my_id}")
        except Exception as e:
            logger.error(f"Failed to start Telegram client: {e}")
            raise

    async def stop(self) -> None:
        """Shutdown Telegram client."""
        self._is_ready = False
        if self._client:
            await self._client.stop()

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
        try:
            msg = await self._client.send_text(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
            return self._convert_message(msg)
        except AioTDLibError as e:
            logger.error(f"Failed to send message: {e}")
            raise RuntimeError(f"Telegram error: {e}")

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str = "",
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[TelegramMessage]:
        """Send a photo to a chat.

        `photo` may be a local file path or a remote Telegram file_id.
        """
        if not self._client:
            raise RuntimeError("Client not initialized")
        try:
            msg = await self._client.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption or None,
                reply_to_message_id=reply_to_message_id,
            )
            return self._convert_message(msg) if msg else None
        except AioTDLibError as e:
            logger.error(f"Failed to send photo: {e}")
            raise RuntimeError(f"Telegram error: {e}")

    async def send_voice(
        self,
        chat_id: int,
        voice: str,
        caption: str = "",
        duration: int = 0,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[TelegramMessage]:
        """Send a voice message (OGG/Opus, local path or file_id)."""
        if not self._client:
            raise RuntimeError("Client not initialized")
        try:
            msg = await self._client.send_voice_note(
                chat_id=chat_id,
                voice_note=voice,
                caption=caption or None,
                duration=duration,
                reply_to_message_id=reply_to_message_id,
            )
            return self._convert_message(msg) if msg else None
        except AioTDLibError as e:
            logger.error(f"Failed to send voice message: {e}")
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
        except AioTDLibError:
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
        except AioTDLibError:
            return None

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 30,
        from_message_id: int = 0,
    ) -> List[TelegramMessage]:
        """Get chat message history (most recent first)."""
        if not self._client:
            return []
        try:
            messages: List[TelegramMessage] = []
            async for msg in self._client.iter_chat_history(
                chat_id=chat_id,
                from_message_id=from_message_id,
                limit=limit,
            ):
                messages.append(self._convert_message(msg))
                if len(messages) >= limit:
                    break
            return messages
        except AioTDLibError as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

    async def open_chat(self, chat_id: int) -> None:
        """Open a chat (mark as read)."""
        if not self._client:
            return
        try:
            await self._client.api.open_chat(chat_id=chat_id)
        except AioTDLibError as e:
            logger.error(f"Failed to open chat: {e}")

    async def close_chat(self, chat_id: int) -> None:
        """Close a chat."""
        if not self._client:
            return
        try:
            await self._client.api.close_chat(chat_id=chat_id)
        except AioTDLibError as e:
            logger.error(f"Failed to close chat: {e}")

    async def view_messages(self, chat_id: int, message_ids: List[int]) -> None:
        """Mark messages as viewed."""
        if not self._client or not message_ids:
            return
        try:
            await self._client.api.view_messages(
                chat_id=chat_id,
                message_ids=message_ids,
                force_read=True,
            )
        except AioTDLibError as e:
            logger.error(f"Failed to view messages: {e}")

    async def react_with_emoji(self, chat_id: int, message_id: int, emoji: str) -> None:
        """React to a message with an emoji."""
        if not self._client:
            return
        try:
            await self._client.api.add_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction_type=td.ReactionTypeEmoji(emoji=emoji),
                is_big=False,
                update_recent_reactions=False,
            )
        except AioTDLibError as e:
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
                from_chat_id=from_chat_id,
                chat_id=to_chat_id,
                message_ids=[message_id],
            )
        except AioTDLibError as e:
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
            await self._client.edit_text(
                chat_id=chat_id,
                message_id=message_id,
                text=new_text,
            )
        except AioTDLibError as e:
            logger.error(f"Failed to edit message: {e}")

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        """Delete a message."""
        if not self._client:
            return
        try:
            await self._client.api.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id],
                revoke=True,
            )
        except AioTDLibError as e:
            logger.error(f"Failed to delete message: {e}")

    async def join_chat_by_link(self, invite_link: str) -> int:
        """Join a chat by invite link. Returns chat ID."""
        if not self._client:
            raise RuntimeError("Client not initialized")
        try:
            chat = await self._client.api.join_chat_by_invite_link(invite_link=invite_link)
            return chat.id
        except AioTDLibError as e:
            logger.error(f"Failed to join chat: {e}")
            raise RuntimeError(f"Failed to join: {e}")

    async def leave_chat(self, chat_id: int) -> None:
        """Leave a chat."""
        if not self._client:
            return
        try:
            await self._client.api.leave_chat(chat_id=chat_id)
        except AioTDLibError as e:
            logger.error(f"Failed to leave chat: {e}")

    async def search_chats(self, query: str) -> List[TelegramChat]:
        """Search chats by name."""
        if not self._client:
            return []
        try:
            result = await self._client.api.search_chats(query=query, limit=20)
            chats = []
            for chat_id in result.chat_ids:
                chat = await self.get_chat(chat_id)
                if chat:
                    chats.append(chat)
            return chats
        except AioTDLibError as e:
            logger.error(f"Failed to search chats: {e}")
            return []

    async def search_messages(
        self,
        chat_id: Optional[int] = None,
        query: str = "",
        limit: int = 10,
    ) -> List[TelegramMessage]:
        """Search messages in a chat, or globally if chat_id is omitted."""
        if not self._client:
            return []
        try:
            if chat_id is not None:
                result = await self._client.api.search_chat_messages(
                    chat_id=chat_id,
                    query=query,
                    from_message_id=0,
                    offset=0,
                    limit=limit,
                )
                messages = result.messages
            else:
                result = await self._client.api.search_messages(
                    query=query,
                    offset="",
                    limit=limit,
                )
                messages = result.messages
            return [self._convert_message(m) for m in messages]
        except AioTDLibError as e:
            logger.error(f"Failed to search messages: {e}")
            return []

    async def get_chats(self, limit: int = 200) -> List[TelegramChat]:
        """Get all chats from the main chat list."""
        if not self._client:
            return []
        try:
            chats = await self._client.get_main_list_chats(limit=limit)
            result = []
            for chat in chats:
                tc = self._convert_chat(chat)
                self._chat_cache[tc.id] = tc
                result.append(tc)
            return result
        except AioTDLibError as e:
            logger.error(f"Failed to get chats: {e}")
            return []

    # ---------- Event handling ----------

    def add_event_handler(self, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a callback for incoming events."""
        self._callbacks.append(callback)

    async def _handle_update(self, client: "Client", update: Any) -> None:
        """Handle TDLib updates and emit events."""
        event = self._convert_update(update)
        if event is None:
            return
        for cb in self._callbacks:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

    def _convert_update(self, update: Any) -> Optional[Dict[str, Any]]:
        """Convert a TDLib update to a dict. Returns None for uninteresting updates."""
        if isinstance(update, td.UpdateNewMessage):
            msg = self._convert_message(update.message)
            return {
                "type": "updateNewMessage",
                "message": msg,
                "chat_id": msg.chat_id,
            }
        elif isinstance(update, td.UpdateUser):
            return {
                "type": "updateUser",
                "user": self._convert_user(update.user),
            }
        elif isinstance(update, (td.UpdateChatLastMessage, td.UpdateChatPosition, td.UpdateChatReadInbox)):
            chat_id = getattr(update, "chat_id", None)
            if chat_id is not None:
                # Invalidate cache so subsequent get_chat() re-fetches fresh data.
                self._chat_cache.pop(chat_id, None)
            return {"type": "updateChat", "chat_id": chat_id}
        return None

    # ---------- Conversion helpers ----------

    def _convert_message(self, msg: Any) -> TelegramMessage:
        """Convert TDLib Message to internal TelegramMessage."""
        content = ""
        media: Optional[Dict[str, Any]] = None
        if msg.content is not None:
            text_field = getattr(msg.content, "text", None)
            caption_field = getattr(msg.content, "caption", None)
            if text_field is not None and hasattr(text_field, "text"):
                content = text_field.text or ""
            elif caption_field is not None and hasattr(caption_field, "text"):
                content = caption_field.text or ""

            if isinstance(msg.content, td.MessageVoiceNote):
                voice_note = msg.content.voice_note
                media = {
                    "type": "voice",
                    "file_id": voice_note.voice.id,
                    "duration": voice_note.duration,
                }
            elif isinstance(msg.content, td.MessagePhoto):
                sizes = msg.content.photo.sizes or []
                if sizes:
                    largest = max(sizes, key=lambda s: s.width * s.height)
                    media = {"type": "photo", "file_id": largest.photo.id}

        sender_id = 0
        if isinstance(msg.sender_id, td.MessageSenderUser):
            sender_id = msg.sender_id.user_id
        elif isinstance(msg.sender_id, td.MessageSenderChat):
            sender_id = msg.sender_id.chat_id

        reply_to_message_id = None
        if msg.reply_to is not None and hasattr(msg.reply_to, "message_id"):
            reply_to_message_id = msg.reply_to.message_id

        return TelegramMessage(
            id=msg.id,
            chat_id=msg.chat_id,
            sender_id=sender_id,
            date=msg.date,
            content=content,
            is_outgoing=bool(getattr(msg, "is_outgoing", False)),
            reply_to_message_id=reply_to_message_id,
            media=media,
        )

    def _convert_chat(self, chat: Any) -> TelegramChat:
        """Convert TDLib Chat to internal TelegramChat."""
        chat_type = "private"
        chat_type_obj = getattr(chat, "type_", None)
        if isinstance(chat_type_obj, td.ChatTypePrivate):
            chat_type = "private"
        elif isinstance(chat_type_obj, td.ChatTypeBasicGroup):
            chat_type = "group"
        elif isinstance(chat_type_obj, td.ChatTypeSupergroup):
            chat_type = "channel" if chat_type_obj.is_channel else "supergroup"
        elif isinstance(chat_type_obj, td.ChatTypeSecret):
            chat_type = "private"

        is_pinned = False
        for pos in (chat.positions or []):
            if pos.is_pinned:
                is_pinned = True
                break

        return TelegramChat(
            id=chat.id,
            title=chat.title or "",
            type=chat_type,
            unread_count=chat.unread_count or 0,
            is_pinned=is_pinned,
            is_member=True,  # membership state isn't exposed on Chat directly
            last_message=self._convert_message(chat.last_message) if chat.last_message else None,
        )

    def _convert_user(self, user: Any) -> TelegramUser:
        """Convert TDLib User to internal TelegramUser."""
        username = ""
        usernames = getattr(user, "usernames", None)
        if usernames is not None and getattr(usernames, "active_usernames", None):
            username = usernames.active_usernames[0]
        return TelegramUser(
            id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=username,
            phone_number=user.phone_number or "",
        )

    # ---------- Additional features ----------

    async def get_contact_ids(self) -> List[int]:
        """Return the user IDs of all Telegram contacts."""
        if not self._client:
            return []
        try:
            result = await self._client.api.get_contacts()
            return list(result.user_ids)
        except AioTDLibError as e:
            logger.error(f"Failed to get contacts: {e}")
            return []

    async def send_typing(self, chat_id: int) -> None:
        """Send typing action."""
        if not self._client:
            return
        try:
            await self._client.api.send_chat_action(
                chat_id=chat_id,
                business_connection_id="",
                action=td.ChatActionTyping(),
            )
        except AioTDLibError as e:
            logger.debug(f"Failed to send typing: {e}")

    async def send_sticker(self, chat_id: int, sticker_file_id: str) -> None:
        """Send a sticker by file ID (or local path)."""
        if not self._client:
            return
        try:
            await self._client.send_sticker(chat_id=chat_id, sticker=sticker_file_id)
        except AioTDLibError as e:
            logger.error(f"Failed to send sticker: {e}")

    async def get_stickers(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get favorite/recently-used stickers."""
        if not self._client:
            return []
        try:
            stickers = await self._client.api.get_stickers(
                sticker_type=td.StickerTypeRegular(),
                limit=limit,
                chat_id=0,
                query="",
            )
            result = []
            for s in stickers.stickers:
                file_id = None
                if s.sticker and s.sticker.remote:
                    file_id = s.sticker.remote.id
                result.append({
                    "id": s.id,
                    "emoji": s.emoji,
                    "file_id": file_id,
                })
            return result
        except AioTDLibError as e:
            logger.error(f"Failed to get stickers: {e}")
            return []

    async def save_sticker(self, sticker_file_id: str) -> bool:
        """Save a sticker (by its remote file_id) to favorites."""
        if not self._client:
            return False
        try:
            await self._client.api.add_favorite_sticker(
                sticker=td.InputFileRemote(id=sticker_file_id),
            )
            return True
        except AioTDLibError as e:
            logger.error(f"Failed to save sticker: {e}")
            return False

    async def ban_chat_member(
        self,
        chat_id: int,
        user_id: int,
        banned_until_date: int = 0,
        revoke_messages: bool = False,
    ) -> bool:
        """Ban a user from a group/supergroup/channel."""
        if not self._client:
            return False
        try:
            await self._client.api.ban_chat_member(
                chat_id=chat_id,
                member_id=td.MessageSenderUser(user_id=user_id),
                banned_until_date=banned_until_date,
                revoke_messages=revoke_messages,
            )
            return True
        except AioTDLibError as e:
            logger.error(f"Failed to ban user {user_id} in chat {chat_id}: {e}")
            return False

    async def set_member_tag(self, chat_id: int, user_id: int, tag: str) -> bool:
        """Best-effort mapping of a free-form 'tag' onto a real TDLib chat member status.

        `tag` in {"admin", "moderator"} promotes to administrator with a
        conservative set of rights; anything else demotes back to a plain
        member.
        """
        if not self._client:
            return False
        try:
            if tag.lower() in ("admin", "moderator", "administrator"):
                status = td.ChatMemberStatusAdministrator(
                    rights=td.ChatAdministratorRights(
                        can_manage_chat=True,
                        can_change_info=False,
                        can_post_messages=False,
                        can_edit_messages=False,
                        can_delete_messages=True,
                        can_invite_users=True,
                        can_restrict_members=True,
                        can_pin_messages=True,
                        can_manage_topics=False,
                        can_promote_members=False,
                        can_manage_video_chats=False,
                        can_post_stories=False,
                        can_edit_stories=False,
                        can_delete_stories=False,
                        is_anonymous=False,
                    ),
                    custom_title=tag,
                    can_be_edited=True,
                )
            else:
                status = td.ChatMemberStatusMember(member_until_date=0)
            await self._client.api.set_chat_member_status(
                chat_id=chat_id,
                member_id=td.MessageSenderUser(user_id=user_id),
                status=status,
            )
            return True
        except AioTDLibError as e:
            logger.error(f"Failed to set tag for user {user_id} in chat {chat_id}: {e}")
            return False

    async def get_file_path(self, file_id: int) -> Optional[str]:
        """Resolve a TDLib numeric file_id to a local downloaded file path, if any."""
        if not self._client:
            return None
        try:
            file = await self._client.api.get_file(file_id=file_id)
            if file.local and file.local.is_downloading_completed:
                return file.local.path
            return None
        except AioTDLibError as e:
            logger.error(f"Failed to get file: {e}")
            return None

    async def download_file_bytes(self, file_id: int) -> Optional[bytes]:
        """Download a file (e.g. a voice note) by its numeric file_id and
        return its raw bytes once the download completes."""
        if not self._client:
            return None
        try:
            file = await self._client.api.download_file(
                file_id=file_id,
                priority=1,
                offset=0,
                limit=0,
                synchronous=True,
            )
            if file.local and file.local.is_downloading_completed and file.local.path:
                return Path(file.local.path).read_bytes()
            return None
        except (AioTDLibError, OSError) as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return None


# Singleton instance
_client: Optional[TelegramClient] = None


def get_telegram_client() -> TelegramClient:
    """Get global Telegram client instance."""
    global _client
    if _client is None:
        _client = TelegramClient()
    return _client
