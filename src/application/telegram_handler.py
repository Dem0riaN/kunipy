"""Telegram event handling.

Handles incoming Telegram events and routes them to workers.
Extracted from app.py god object (ТЗ-001 punkt 5).
"""

import logging
import random

from ..di import Dependencies
from ..domain.models import TelegramMessage
from ..interfaces.worker import Notification
from .media_service import MediaService

logger = logging.getLogger(__name__)


class TelegramEventHandler:
    """Handles incoming Telegram events.

    Responsibilities:
    1. Process new messages
    2. Apply lockdown/access control
    3. Transcribe voice messages
    4. Describe photos (vision)
    5. Format notifications
    6. Route to notification manager

    Based on C++ kuni event handling pattern.
    """

    def __init__(self, deps: Dependencies):
        """Initialize event handler.

        Args:
            deps: Dependency injection container
        """
        self._deps = deps
        self._current_chat_id: int | None = None

        # Initialize media service
        self._media_service = MediaService(
            telegram_client=deps.telegram_client,
            openai_client=deps.openai_chat,
            config=deps.config
        )

    async def handle_event(self, event: dict) -> None:
        """Handle incoming Telegram event.

        Args:
            event: TDLib event dictionary
        """
        event_type = event.get("type")

        if event_type == "updateNewMessage":
            msg = event.get("message")
            if msg:
                await self.handle_new_message(msg)

        elif event_type == "updateChat":
            chat = event.get("chat")
            if chat:
                await self._handle_chat_update(chat)

        elif event_type == "updateUser":
            # User updated - cache invalidation if needed
            pass

    async def handle_new_message(self, msg: TelegramMessage) -> None:
        """Handle a new incoming message.

        Implements ТЗ-001 punkt 4: message processing pipeline.

        Args:
            msg: Telegram message
        """
        # Ignore own messages
        if msg.is_outgoing:
            return

        # Check lockdown mode
        if not await self._is_accessible(msg.chat_id):
            logger.debug(f"Message from {msg.chat_id} blocked by lockdown")
            return

        # Apply notification filter
        if not await self._check_notification_filter(msg.chat_id):
            logger.debug(f"Message from {msg.chat_id} filtered out")
            return

        # Random ignore chance (except for papik)
        if await self._should_ignore_randomly(msg):
            logger.debug(f"Randomly ignoring message from {msg.chat_id}")
            return

        # Process media (transcribe voice, describe photos)
        await self._process_media(msg)

        # Build notification
        notification_text = await self._format_notification(msg)
        if not notification_text:
            return

        # Determine priority
        priority = await self._calculate_priority(msg)

        # Create notification with chat pin
        notification = Notification(
            message=notification_text,
            priority=priority,
            pin=f"chat_{msg.chat_id}",  # Worker affinity by chat
            metadata={
                "chat_id": msg.chat_id,
                "message_id": msg.message_id,
                "sender_id": msg.user_id,
            }
        )

        # Pass to notification manager
        await self._deps.notification_manager.pass_notification(
            message=notification.message,
            priority=notification.priority,
            pin=notification.pin,
            metadata=notification.metadata
        )

        logger.debug(f"Notification created for chat {msg.chat_id}, priority={priority}")

    async def send_startup_notifications(self) -> None:
        """Send notifications for unread chats on startup.

        Implements ТЗ-001 punkt 4: startup notification scan.
        """
        if not self._deps.config.check_chats_on_startup:
            return

        if not self._deps.telegram_client:
            return

        logger.info("Scanning for unread chats on startup...")

        chats = await self._deps.telegram_client.get_chats(limit=50)

        # Process oldest first (reverse order)
        for chat in reversed(chats):
            if chat.unread_count == 0:
                continue

            # Get last message
            if chat.last_message:
                await self.handle_new_message(chat.last_message)
            else:
                # Fetch last message
                hist = await self._deps.telegram_client.get_chat_history(chat.id, limit=1)
                if hist:
                    await self.handle_new_message(hist[0])

        logger.info(f"Startup notifications sent for {len([c for c in chats if c.unread_count > 0])} chats")

    async def _is_accessible(self, chat_id: int) -> bool:
        """Check if chat is accessible under lockdown mode.

        Args:
            chat_id: Chat ID

        Returns:
            True if accessible
        """
        return await self._check_lockdown(chat_id, self._deps.config.lockdown)

    async def _check_notification_filter(self, chat_id: int) -> bool:
        """Check if chat should generate notifications.

        Separate from accessibility - can be in a chat but not get notified.

        Args:
            chat_id: Chat ID

        Returns:
            True if should notify
        """
        return await self._check_lockdown(chat_id, self._deps.config.chat_notification_filter)

    async def _check_lockdown(self, chat_id: int, mode) -> bool:
        """Evaluate lockdown mode against chat.

        Args:
            chat_id: Chat ID
            mode: LockdownMode

        Returns:
            True if allowed
        """
        if mode.value == "none":
            return True

        if mode.value == "papik_only":
            return chat_id == self._deps.config.papik_chat_id

        if mode.value == "contacts_only":
            chat = await self._deps.telegram_client.get_chat(chat_id)
            if not chat or chat.type != "private":
                return True
            contact_ids = await self._deps.telegram_client.get_contact_ids()
            return chat_id in contact_ids

        return True

    async def _should_ignore_randomly(self, msg: TelegramMessage) -> bool:
        """Determine if should randomly ignore message.

        Makes character seem less robotically attentive.
        Never ignores papik (owner).

        Args:
            msg: Message

        Returns:
            True if should ignore
        """
        if msg.user_id == self._deps.config.papik_chat_id:
            return False

        return random.random() < self._deps.config.suggest_ignore_chance

    async def _process_media(self, msg: TelegramMessage) -> None:
        """Process media in message (voice transcription, photo description).

        Args:
            msg: Message (modified in place)
        """
        if not msg.media:
            return

        media_type = msg.media.get("type")

        # Transcribe voice messages
        if media_type == "voice" and not msg.text:
            transcription = await self._media_service.transcribe_voice_message(msg)
            if transcription:
                msg.text = transcription

        # Describe photos
        elif media_type == "photo":
            description = await self._media_service.describe_photo_message(msg)
            if description:
                msg.text = f"{msg.text}\n[photo] {description}".strip()

    async def _format_notification(self, msg: TelegramMessage) -> str:
        """Format message as notification string.

        Args:
            msg: Message

        Returns:
            Notification text
        """
        chat = await self._deps.telegram_client.get_chat(msg.chat_id)
        chat_title = chat.title if chat else f"Chat {msg.chat_id}"

        # Get sender info
        sender_name = "Unknown"
        if msg.user_id:
            user = await self._deps.telegram_client.get_user(msg.user_id)
            if user:
                sender_name = f"{user.first_name} {user.last_name}".strip() or \
                              user.username or f"user_{msg.user_id}"

        # Format based on chat type
        is_dm = chat and chat.type == "private"

        if is_dm:
            return (
                f'<notification chat_id="{msg.chat_id}">\n'
                f"You received a direct message from {sender_name} (chat_id={msg.chat_id})\n"
                f"{msg.text}\n"
                f"</notification>\n"
                f"You don't have any chat open. Use #open tool to open the chat"
            )
        else:
            return (
                f'<notification chat_id="{msg.chat_id}">\n'
                f'{sender_name} sent a message in group chat "{chat_title}" (chat_id={msg.chat_id})\n'
                f"{msg.text}\n"
                f"</notification>\n"
                f"You don't have any chat open. Use #open tool to open the chat"
            )

    async def _calculate_priority(self, msg: TelegramMessage) -> int:
        """Calculate notification priority.

        Args:
            msg: Message

        Returns:
            Priority (higher = more important)
        """
        priority = 0

        # Papik (owner) gets highest priority
        if msg.user_id == self._deps.config.papik_chat_id:
            priority = 1000

        # Pinned chats get elevated priority
        elif self._deps.config.wake_up_on_pinned_chat:
            chat = await self._deps.telegram_client.get_chat(msg.chat_id)
            if chat and chat.is_pinned:
                priority = 100

        return priority

    async def _handle_chat_update(self, chat: dict) -> None:
        """Handle chat update event (title change, pinned status, etc).

        Args:
            chat: Chat data
        """
        # Could update cache or trigger reactions
