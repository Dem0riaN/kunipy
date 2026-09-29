"""Telegram event handling.

Handles incoming Telegram events and routes them to workers.
Extracted from app.py god object (ТЗ-001 punkt 5).
"""

import logging
import random

from ..di import Dependencies
from ..domain.models import TelegramMessage
from ..interfaces.worker import Notification

logger = logging.getLogger(__name__)


class TelegramEventHandler:
    """Handles incoming Telegram events.

    Responsibilities:
    1. Route Telegram events to appropriate handlers
    2. Apply lockdown/access control
    3. Process media (transcribe voice, describe photos)
    4. Create and enqueue notifications

    Business logic delegated to TelegramMessageService (Sprint 3 Task 2).

    Based on C++ kuni event handling pattern.
    """

    def __init__(self, deps: Dependencies):
        """Initialize event handler.

        Args:
            deps: Dependency injection container
        """
        self._deps = deps
        self._current_chat_id: int | None = None

        # Use injected services (Sprint 3)
        self._media_service = deps.media_service
        self._message_service = deps.telegram_message_service

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

        # Store incoming message to memory (ТЗ-002)
        if self._deps.memory_service:
            try:
                await self._deps.memory_service.store_message(
                    user_id=str(msg.user_id),
                    chat_id=str(msg.chat_id),
                    channel="telegram",
                    role="user",
                    content=msg.text or "",
                    message_id=str(getattr(msg, 'message_id', getattr(msg, 'id', 0))),
                    metadata={
                        "media_type": msg.media.get("type") if msg.media else None,
                        "is_voice": bool(msg.media and msg.media.get("type") == "voice"),
                    }
                )
                logger.debug("Stored user message to memory system")
            except Exception as e:
                logger.warning(f"Failed to store message to memory: {e}")

        # Mark message as read immediately and show typing indicator
        message_id = getattr(msg, 'message_id', getattr(msg, 'id', 0))
        await self._message_service.mark_as_read_and_typing(msg.chat_id, message_id)

        # Process media (transcribe voice, describe photos)
        await self._process_media(msg)

        # Build notification using message service
        notification_text = await self._message_service.format_notification(msg)
        if not notification_text:
            logger.warning(f"Failed to format notification for chat {msg.chat_id}")
            return

        logger.debug(f"Notification text created: {notification_text[:100]}...")

        # Determine priority using message service
        priority = await self._message_service.calculate_priority(msg)
        logger.debug(f"Message priority: {priority}")

        # Check if message has image media for multimodal content
        has_image_media = self._message_service.has_image_media(msg)

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

    async def _handle_chat_update(self, chat: dict) -> None:
        """Handle chat update event (title change, pinned status, etc).

        Args:
            chat: Chat data
        """
        # Could update cache or trigger reactions
