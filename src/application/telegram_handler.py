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

        # Initialize media service with extractor registry
        self._media_service = MediaService(
            telegram_client=deps.telegram_client,
            openai_client=deps.openai_chat,
            config=deps.config,
            extractor_registry=deps.extractor_registry
        )

    async def handle_event(self, event: dict) -> None:
        """Handle incoming Telegram event.

        Args:
            event: TDLib event dictionary
        """
        event_type = event.get("type")
        logger.info(f"Received Telegram event: {event_type}")

        if event_type == "updateNewMessage":
            msg = event.get("message")
            if msg:
                logger.info(f"Processing new message from chat {msg.chat_id}")
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
            logger.debug(f"Ignoring outgoing message from chat {msg.chat_id}")
            return

        # Check lockdown mode
        if not await self._is_accessible(msg.chat_id):
            logger.info(f"Message from {msg.chat_id} blocked by lockdown")
            return

        # Apply notification filter
        if not await self._check_notification_filter(msg.chat_id):
            logger.info(f"Message from {msg.chat_id} filtered by notification filter")
            return

        # Random ignore chance (except for papik)
        if await self._should_ignore_randomly(msg):
            logger.info(f"Randomly ignoring message from {msg.chat_id}")
            return

        logger.info(f"Processing message from chat {msg.chat_id}, user {msg.user_id}")

        # Mark message as read immediately and show typing indicator
        message_id = getattr(msg, 'message_id', getattr(msg, 'id', 0))
        if message_id and self._deps.telegram_client:
            try:
                await self._deps.telegram_client.view_messages(msg.chat_id, [message_id])
                logger.debug(f"Marked message {message_id} in chat {msg.chat_id} as read")
                # Show typing indicator immediately
                await self._deps.telegram_client.send_typing(msg.chat_id)
                logger.debug(f"Sent typing indicator to chat {msg.chat_id}")
            except (ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.warning(f"Failed to mark message as read or send typing: {e}")

        # Process media (transcribe voice, describe photos)
        await self._process_media(msg)

        # Build notification
        notification_text = await self._format_notification(msg)
        if not notification_text:
            logger.warning(f"Failed to format notification for chat {msg.chat_id}")
            return

        logger.debug(f"Notification text created: {notification_text[:100]}...")

        # Determine priority
        priority = await self._calculate_priority(msg)
        logger.debug(f"Message priority: {priority}")

        # Check if message has image media for multimodal content
        has_image_media = msg.media and msg.media.get("type") in ("photo", "sticker")

        # Create notification with chat pin
        notification = Notification(
            message=notification_text,
            priority=priority,
            pin=f"chat_{msg.chat_id}",  # Worker affinity by chat
            metadata={
                "chat_id": msg.chat_id,
                "message_id": getattr(msg, 'message_id', getattr(msg, 'id', 0)),
                "sender_id": msg.user_id,
                "has_image_media": has_image_media,
                "telegram_message": msg if has_image_media else None,
            }
        )

        # Pass to notification manager
        logger.info(f"Passing notification to manager for chat {msg.chat_id}")
        await self._deps.notification_manager.pass_notification(
            message=notification.message,
            priority=notification.priority,
            pin=notification.pin,
            metadata=notification.metadata
        )

        logger.info(f"Notification passed successfully for chat {msg.chat_id}, priority={priority}")

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
        result = await self._check_lockdown(chat_id, self._deps.config.lockdown)
        logger.debug(f"Lockdown check for chat {chat_id}: mode={self._deps.config.lockdown.value}, papik_chat_id={self._deps.config.papik_chat_id}, result={result}")
        return result

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
            # Allow papik's chat (can be user ID or chat ID)
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
        # Check both user_id and chat_id for papik
        if hasattr(msg, 'user_id') and msg.user_id == self._deps.config.papik_chat_id:
            return False
        if msg.chat_id == self._deps.config.papik_chat_id:
            return False

        return random.random() < self._deps.config.suggest_ignore_chance

    async def _process_media(self, msg: TelegramMessage) -> None:
        """Process media in message (voice transcription, text documents).

        For photos/stickers, media metadata is preserved for multimodal content creation.
        This method only processes voice and text documents that need preprocessing.

        Args:
            msg: Message (modified in place)
        """
        if not msg.media:
            return

        media_type = msg.media.get("type")
        logger.info(f"Processing media type: {media_type}")

        # Transcribe voice messages
        if media_type == "voice" and not msg.text:
            transcription = await self._media_service.transcribe_voice_message(msg)
            if transcription:
                msg.text = transcription

        # Read text documents (.txt, .md)
        elif media_type == "document":
            logger.info(f"Reading text document, file_name: {msg.media.get('file_name')}")
            doc_text = await self._media_service.read_text_document(msg)
            logger.info(f"Document text length: {len(doc_text) if doc_text else 0}")
            if doc_text:
                msg.text = f"{msg.text}\n{doc_text}".strip()
                logger.info("Updated msg.text with document content")

        # Photos and stickers: keep media metadata for multimodal content creation
        # (handled in worker when creating Message objects)

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
        sender_id = msg.user_id
        if sender_id:
            user = await self._deps.telegram_client.get_user(sender_id)
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

    async def _calculate_priority(self, msg: TelegramMessage) -> int:
        """Calculate notification priority.

        Args:
            msg: Message

        Returns:
            Priority (higher = more important)
        """
        priority = 0

        # Papik (owner) gets highest priority
        # Check both user_id/sender_id and chat_id
        sender_id = msg.user_id
        if sender_id == self._deps.config.papik_chat_id or msg.chat_id == self._deps.config.papik_chat_id:
            priority = 1000

        return priority

    async def _handle_chat_update(self, chat: dict) -> None:
        """Handle chat update event (title change, pinned status, etc).

        Args:
            chat: Chat data
        """
        # Could update cache or trigger reactions
