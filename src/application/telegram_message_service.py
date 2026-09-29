"""Telegram message business logic service.

Handles Telegram message operations separate from event routing.
Extracted from telegram_handler.py for better separation of concerns (Sprint 3).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config
    from ..domain.models import TelegramMessage
    from ..interfaces import IMemoryStore, ITelegramClient

logger = logging.getLogger(__name__)


class TelegramMessageService:
    """Service for Telegram message business operations.

    Responsibilities:
    - Mark messages as read
    - Send typing indicators
    - Store messages to memory
    - Calculate message priority
    - Format notification text

    Separated from TelegramEventHandler for better separation of concerns.
    """

    def __init__(
        self,
        telegram_client: ITelegramClient | None,
        memory_store: IMemoryStore | None,
        config: Config,
    ):
        """Initialize message service.

        Args:
            telegram_client: Telegram client for API operations
            memory_store: Memory storage for message persistence
            config: Application configuration
        """
        self._telegram = telegram_client
        self._memory = memory_store
        self._config = config

    async def mark_as_read_and_typing(self, chat_id: int, message_id: int) -> bool:
        """Mark message as read and show typing indicator.

        Args:
            chat_id: Chat identifier
            message_id: Message identifier

        Returns:
            True if successful, False otherwise
        """
        if not self._telegram or not message_id:
            return False

        # Retry logic with exponential backoff (Sprint 3 Task 3)
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                await self._telegram.view_messages(chat_id, [message_id])
                logger.debug(f"Marked message {message_id} in chat {chat_id} as read")

                # Show typing indicator (best effort, don't retry)
                try:
                    await self._telegram.send_typing(chat_id)
                    logger.debug(f"Sent typing indicator to chat {chat_id}")
                except Exception as e:
                    logger.debug(f"Typing indicator failed (non-critical): {e}")

                return True

            except (OSError, ValueError, KeyError, TypeError, RuntimeError, TimeoutError) as e:
                if attempt == max_retries:
                    logger.warning(
                        f"Failed to mark message as read after {max_retries} retries: {e}"
                    )
                    return False

                logger.debug(
                    f"Read receipt attempt {attempt + 1}/{max_retries + 1} failed, retrying..."
                )
                await asyncio.sleep(0.3 * (2 ** attempt))

        return False

    async def store_to_memory(self, msg: TelegramMessage) -> None:
        """Store incoming message to memory store.

        Args:
            msg: Telegram message to store
        """
        if not self._memory or not self._config.memory_enabled:
            return

        try:
            # Store message content
            from ..domain.memory_models import ConversationMessage

            conv_msg = ConversationMessage(
                chat_id=msg.chat_id,
                message_id=getattr(msg, 'message_id', getattr(msg, 'id', 0)),
                sender_id=msg.user_id,
                text=msg.text or "",
                timestamp=msg.timestamp,
                is_bot=False,
            )

            await self._memory.add_message(conv_msg)
            logger.debug(f"Stored message to memory: chat={msg.chat_id}")
        except Exception as e:
            logger.warning(f"Failed to store message to memory: {e}")

    async def calculate_priority(self, msg: TelegramMessage) -> int:
        """Calculate message priority based on various factors.

        Args:
            msg: Telegram message

        Returns:
            Priority value (higher = more urgent)
        """
        priority = 0

        # Papik (owner) gets highest priority
        # Check both user_id/sender_id and chat_id
        sender_id = msg.user_id
        if sender_id == self._config.papik_chat_id or msg.chat_id == self._config.papik_chat_id:
            priority = 1000

        return priority

    async def format_notification(self, msg: TelegramMessage) -> str | None:
        """Format notification text from Telegram message.

        Args:
            msg: Telegram message

        Returns:
            Formatted notification text or None if formatting fails
        """
        try:
            # Get chat info
            chat = await self._telegram.get_chat(msg.chat_id)
            chat_title = chat.title if chat else f"Chat {msg.chat_id}"

            # Get sender info
            sender_name = "Unknown"
            sender_id = msg.user_id
            if sender_id:
                user = await self._telegram.get_user(sender_id)
                if user:
                    sender_name = f"{user.first_name} {user.last_name}".strip() or \
                                  user.username or f"user_{sender_id}"

            # Get message text (handle both 'text' and 'content' fields)
            msg_text = getattr(msg, 'text', getattr(msg, 'content', ''))

            # Format based on chat type
            is_dm = chat and chat.type == "private"

            if is_dm:
                return (
                    f'<notification chat_id="{msg.chat_id}">\n'
                    f"You received a direct message from {sender_name} (chat_id={msg.chat_id})\n"
                    f"{msg_text}\n"
                    f"</notification>\n"
                    f"You don't have any chat open. Use #open tool to open the chat"
                )
            else:
                return (
                    f'<notification chat_id="{msg.chat_id}">\n'
                    f'{sender_name} sent a message in group chat "{chat_title}" (chat_id={msg.chat_id})\n'
                    f"{msg_text}\n"
                    f"</notification>\n"
                    f"You don't have any chat open. Use #open tool to open the chat"
                )

        except Exception as e:
            logger.error(f"Failed to format notification: {e}")
            return None

    def has_image_media(self, msg: TelegramMessage) -> bool:
        """Check if message contains image media (photo or sticker).

        Args:
            msg: Telegram message

        Returns:
            True if message has image media
        """
        return bool(msg.media and msg.media.get("type") in ("photo", "sticker"))
