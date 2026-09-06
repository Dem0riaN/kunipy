"""Worker for kunipy.

A worker pulls notifications from the queue and processes them using LLM.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from .config import get_config
from .diary import Diary
from .notification_manager import Notification, NotificationManager
from .openai_chat import OpenAIChat
from .telegram_client import TelegramClient, TelegramMessage
from .tools import ToolContext

logger = logging.getLogger(__name__)


class Worker:
    """A worker that processes notifications and generates responses."""

    def __init__(
        self,
        name: str,
        app_base: Any,  # App instance (for callbacks)
        telegram: Optional[TelegramClient],
        openai: Optional[OpenAIChat],
        diary: Optional[Diary],
        notification_manager: NotificationManager,
    ):
        self.name = name
        self.app = app_base
        self.telegram = telegram
        self.openai = openai
        self.diary = diary
        self.notification_manager = notification_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.temporary_context: List[Any] = []  # messages for current conversation
        self._sleeping = False
        self._wake_event = asyncio.Event()
        self.config = get_config()

    async def run(self) -> None:
        """Main worker loop."""
        self._running = True
        logger.info(f"Worker {self.name} started")

        while self._running:
            try:
                # Get next notification (blocking)
                notification = await self.notification_manager.get()
                if notification is None:
                    # Manager stopped
                    break

                # Process the notification
                await self._process_notification(notification)

                # After processing, optionally go to sleep (idle)
                await self._maybe_sleep()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Worker {self.name} error: {e}")
                await asyncio.sleep(1)  # backoff

        logger.info(f"Worker {self.name} stopped")

    async def _process_notification(self, notification: Notification) -> None:
        """Process a single notification."""
        logger.debug(f"Worker {self.name} processing {notification._id}")

        # Extract chat_id from pin
        chat_id = None
        if notification.pin.startswith("chat_"):
            try:
                chat_id = int(notification.pin.split("_")[1])
            except (IndexError, ValueError):
                pass

        if chat_id is None:
            logger.warning(f"Notification {notification._id} has invalid pin, skipping")
            return

        # Build context
        context = self._build_context(notification, chat_id)

        # Generate response using LLM
        response = await self._generate_response(context, chat_id)

        if response:
            # Send response via Telegram
            if self.telegram:
                try:
                    await self.telegram.send_message(chat_id, response)
                    logger.info(f"Worker {self.name} sent response to chat {chat_id}")
                    # Store in context
                    self.temporary_context.append({"role": "assistant", "content": response})
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")

    def _build_context(self, notification: Notification, chat_id: int) -> Dict[str, Any]:
        """Build context for LLM from notification and diary."""
        context = {
            "chat_id": chat_id,
            "message": notification.message,
            "actions": notification.actions,
        }
        # Optionally fetch recent history
        return context

    async def _generate_response(self, context: Dict[str, Any], chat_id: int) -> Optional[str]:
        """Generate a response using LLM."""
        if not self.openai:
            logger.warning("No OpenAI client, skipping response generation")
            return None

        # For now, simple echo (TODO: implement proper LLM call)
        # In a real implementation, we would call self.openai.chat with a system prompt
        # and the notification message.
        return f"Echo from {self.name}: {context.get('message', '')[:100]}"

    async def _maybe_sleep(self) -> None:
        """Randomly go to sleep if configured."""
        if not self.config.randomly_go_sleep:
            return
        # Sleep with low probability (e.g., 5% chance after each notification)
        if random.random() < 0.05:
            sleep_time = random.randint(10, 60)  # seconds
            logger.info(f"Worker {self.name} sleeping for {sleep_time}s")
            self._sleeping = True
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                pass
            self._sleeping = False

    def wake_up(self) -> None:
        """Wake up the worker if sleeping."""
        if self._sleeping:
            logger.info(f"Waking up worker {self.name}")
            self._wake_event.set()
            # We can't easily interrupt asyncio.sleep, so we rely on the loop to check.

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
