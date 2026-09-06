"""Main application for kunipy.

Orchestrates Telegram client, diary, workers, and proxy server.
Supports both Telegram mode (with real client) and standalone proxy mode.
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_config, load_config
from .diary import Diary
from .notification_manager import Notification, NotificationManager, get_notification_manager
from .openai_chat import OpenAIChat
from .telegram_client import TelegramClient, get_telegram_client, TelegramChat, TelegramMessage
from .tools import ToolContext
from .worker import Worker

logger = logging.getLogger(__name__)


class App:
    """Main application class."""

    def __init__(self, working_dir: str = "data"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)

        self.config = get_config()
        self.telegram: Optional[TelegramClient] = None
        self.openai: Optional[OpenAIChat] = None
        self.diary: Optional[Diary] = None
        self.notification_manager: Optional[NotificationManager] = None
        self.workers: List[Worker] = []
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._current_chat_id: Optional[int] = None
        self._proactive_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing kunipy...")

        # OpenAI client
        self.openai = OpenAIChat()

        # Diary
        diary_dir = self.working_dir / "diary"
        self.diary = Diary(diary_dir=diary_dir, openai=self.openai)

        # Notification manager
        self.notification_manager = get_notification_manager()

        # Telegram client
        if self.config.telegram_enabled:
            self.telegram = get_telegram_client()
            await self.telegram.start()
            self.telegram.add_event_handler(self._handle_telegram_event)
            logger.info(f"Telegram client ready, my_id={self.telegram.my_id}")
        else:
            logger.info("Telegram disabled, running in standalone mode")

        # Register notification handler (routes to workers)
        self.notification_manager.register_handler(self._handle_notification)

        # Create workers
        worker_count = max(1, self.config.worker_count)
        for i in range(worker_count):
            worker = Worker(
                name=f"worker_{i}",
                app_base=self,
                telegram=self.telegram,
                openai=self.openai,
                diary=self.diary,
                notification_manager=self.notification_manager,
            )
            self.workers.append(worker)

        logger.info(f"Initialized with {worker_count} workers")

    async def start(self) -> None:
        """Start the application."""
        self._running = True

        # Start notification manager (this runs the queue loop)
        self.notification_manager.start(len(self.workers))

        # Start workers
        for worker in self.workers:
            task = asyncio.create_task(worker.run(), name=f"worker-{worker.name}")
            self._tasks.append(task)

        # If Telegram is enabled, send startup notifications and start proactive messaging
        if self.config.telegram_enabled and self.telegram:
            await self._send_startup_notifications()
            self._proactive_task = asyncio.create_task(self._proactive_loop())

        # Start proxy server if enabled
        if self.config.proxy_enabled:
            await self._start_proxy_server()

        logger.info("Kunipy is running")

        # Wait for tasks (block until interrupted)
        try:
            # Wait for all worker tasks, but don't exit on one failure
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Shut down the application."""
        if not self._running:
            return
        self._running = False
        logger.info("Stopping...")

        # Cancel proactive loop
        if self._proactive_task and not self._proactive_task.done():
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except asyncio.CancelledError:
                pass

        # Stop notification manager
        if self.notification_manager:
            self.notification_manager.stop()

        # Stop Telegram client
        if self.telegram:
            await self.telegram.stop()

        # Cancel worker tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Dump remaining context to diary
        for worker in self.workers:
            await self.diary_dump_messages(worker.temporary_context)
            worker.temporary_context = []

        logger.info("Stopped")

    # ---------- Telegram event handling ----------

    async def _handle_telegram_event(self, event: Dict[str, Any]) -> None:
        """Handle incoming Telegram events."""
        event_type = event.get("type")
        if event_type == "updateNewMessage":
            msg = event.get("message")
            if msg:
                await self._handle_new_message(msg)
        elif event_type == "updateChat":
            # Chat updated (e.g., title change, pinned status)
            chat = event.get("chat")
            if chat:
                # Update cache or trigger something
                pass
        elif event_type == "updateUser":
            # User updated
            pass

    async def _handle_new_message(self, msg: TelegramMessage) -> None:
        """Handle a new incoming message from Telegram."""
        # Ignore own messages (sent by us)
        if msg.is_outgoing:
            return

        # Check lockdown mode
        if not await self._is_accessible(msg.chat_id):
            return

        # Build notification string
        notification_text = await self._format_message_notification(msg)
        if not notification_text:
            return

        # Build actions (open chat handler)
        actions = [
            {
                "name": "open",
                "description": f"Open chat {msg.chat_id}",
                "handler": lambda ctx, chat_id=msg.chat_id: self._open_chat(chat_id),
            }
        ]

        # Determine priority
        priority = 0
        if msg.sender_id == self.config.papik_chat_id:
            priority = 1000  # Highest priority for owner
        elif self.config.wake_up_on_pinned_chat:
            # Check if chat is pinned
            chat = await self.telegram.get_chat(msg.chat_id)
            if chat and chat.is_pinned:
                priority = 100

        # Create notification
        notification = Notification(
            priority=priority,
            message=notification_text,
            pin=f"chat_{msg.chat_id}",
            actions=actions,
        )

        self.notification_manager.add_notification(notification)

        # Wake up workers if high priority
        if priority > 0:
            for worker in self.workers:
                worker.wake_up()

    async def _format_message_notification(self, msg: TelegramMessage) -> str:
        """Format a TelegramMessage as a notification string."""
        chat = await self.telegram.get_chat(msg.chat_id)
        if not chat:
            chat_title = f"Chat {msg.chat_id}"
        else:
            chat_title = chat.title

        # Get sender info
        sender_name = "Unknown"
        if msg.sender_id:
            user = await self.telegram.get_user(msg.sender_id)
            if user:
                sender_name = f"{user.first_name} {user.last_name}".strip() or user.username or f"user_{msg.sender_id}"

        # Determine message type
        is_dm = chat and chat.type == "private"

        if is_dm:
            return (
                f'<notification chat_id="{msg.chat_id}">\n'
                f"You received a direct message from {sender_name} (chat_id={msg.chat_id})\n"
                f"{msg.content}\n"
                f"</notification>\n"
                f"You don't have any chat open. Use #open tool to open the chat"
            )
        else:
            return (
                f'<notification chat_id="{msg.chat_id}">\n'
                f"{sender_name} sent a message in group chat \"{chat_title}\" (chat_id={msg.chat_id})\n"
                f"{msg.content}\n"
                f"</notification>\n"
                f"You don't have any chat open. Use #open tool to open the chat"
            )

    async def _is_accessible(self, chat_id: int) -> bool:
        """Check if chat is accessible under lockdown mode."""
        config = get_config()
        if config.lockdown.value == "none":
            return True
        if config.lockdown.value == "papik_only":
            return chat_id == config.papik_chat_id
        if config.lockdown.value == "contacts_only":
            # Check if user is in contacts
            # For now, we assume all accessible, but in real impl we'd check contact list
            return True
        return True

    async def _open_chat(self, chat_id: int) -> str:
        """Open a chat and load history."""
        if not self.telegram:
            return "Telegram not available"

        await self.telegram.open_chat(chat_id)
        self._current_chat_id = chat_id

        chat = await self.telegram.get_chat(chat_id)
        if not chat:
            return f"Chat {chat_id} not found"

        # Load recent messages
        messages = await self.telegram.get_chat_history(chat_id, limit=30)

        # Mark messages as viewed
        if messages:
            msg_ids = [m.id for m in messages]
            await self.telegram.view_messages(chat_id, msg_ids)

        # Build response with chat history
        result = f"You switched to the chat \"{chat.title}\". You see last messages:\n"
        for msg in reversed(messages):  # oldest first for reading order
            sender = await self.telegram.get_user(msg.sender_id)
            sender_name = sender.first_name if sender else f"user_{msg.sender_id}"
            result += f"[{sender_name}]: {msg.content[:200]}\n"

        return result

    async def _send_startup_notifications(self) -> None:
        """Send notifications for unread chats on startup."""
        if not self.config.check_chats_on_startup:
            return
        if not self.telegram:
            return

        chats = await self.telegram.get_chats(limit=50)
        # Process oldest first (reverse order)
        for chat in reversed(chats):
            if chat.unread_count == 0:
                continue
            # Get last message
            if chat.last_message:
                await self._handle_new_message(chat.last_message)
            else:
                # Try to fetch last message
                hist = await self.telegram.get_chat_history(chat.id, limit=1)
                if hist:
                    await self._handle_new_message(hist[0])

    # ---------- Proactive messaging ----------

    async def _proactive_loop(self) -> None:
        """Background loop for proactive messages (writing first).

        This implements the "act proactively" feature from the original kuni:
        - Periodically check pinned chats and important contacts
        - If enough time has passed since last interaction, send a message
        - Use diary to recall context and generate appropriate content
        """
        if not self.telegram:
            return

        logger.info("Proactive loop started")

        # Interval: check every 30-60 minutes
        check_interval_min = 30
        check_interval_max = 60

        while self._running:
            try:
                # Wait for a random interval
                interval = random.randint(check_interval_min * 60, check_interval_max * 60)
                await asyncio.sleep(interval)

                if not self._running:
                    break

                # Check if we should act proactively
                if not self._should_act_proactively():
                    continue

                # Get chats to consider
                chats = await self._get_proactive_chats()
                if not chats:
                    continue

                # Pick a random chat from the list
                chat = random.choice(chats)
                if not chat:
                    continue

                # Generate proactive message
                message = await self._generate_proactive_message(chat)
                if message:
                    await self.telegram.send_message(chat.id, message)
                    logger.info(f"Proactive message sent to {chat.title} ({chat.id})")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in proactive loop: {e}")
                await asyncio.sleep(60)  # backoff on error

        logger.info("Proactive loop stopped")

    def _should_act_proactively(self) -> bool:
        """Determine if it's time to act proactively."""
        # Random chance: 15% per check (so about 1-2 times per day)
        if random.random() > 0.15:
            return False
        return True

    async def _get_proactive_chats(self) -> List[TelegramChat]:
        """Get chats that are candidates for proactive messages.

        Prioritizes:
        1. Pinned chats (high priority)
        2. Chats with recent activity (last 24h)
        3. Chats with papik (owner)
        4. Random chats from main list
        """
        if not self.telegram:
            return []

        all_chats = await self.telegram.get_chats(limit=100)
        candidates = []

        for chat in all_chats:
            # Skip channels (can't send messages)
            if chat.type == "channel":
                continue
            # Skip chats we're not a member of
            if not chat.is_member:
                continue
            # Skip empty chats
            if not chat.last_message:
                continue

            # Check if last message is from us (we already talked recently)
            if chat.last_message and chat.last_message.is_outgoing:
                # If last message is from us and less than 2 hours ago, skip
                last_date = datetime.fromtimestamp(chat.last_message.date)
                if datetime.now() - last_date < timedelta(hours=2):
                    continue
            else:
                # If last message from someone else less than 30 min ago, skip (we might still be in conversation)
                if chat.last_message and not chat.last_message.is_outgoing:
                    last_date = datetime.fromtimestamp(chat.last_message.date)
                    if datetime.now() - last_date < timedelta(minutes=30):
                        continue

            candidates.append(chat)

        # Prioritize: pinned chats first, then owner's chat, then others
        def priority(c: TelegramChat) -> tuple[int, int]:
            p = 0
            if c.is_pinned:
                p += 100
            if c.id == self.config.papik_chat_id:
                p += 50
            # Prefer chats with older last message (we haven't talked in a while)
            age = 0
            if c.last_message:
                age = int((datetime.now() - datetime.fromtimestamp(c.last_message.date)).total_seconds())
            return (p, age)

        candidates.sort(key=priority, reverse=True)
        return candidates[:10]  # top 10

    async def _generate_proactive_message(self, chat: TelegramChat) -> Optional[str]:
        """Generate a proactive message using LLM and diary context."""
        if not self.openai or not self.diary:
            return None

        # Get recent diary entries for context
        # Use a generic query about the chat or recent events
        query = f"What have I been thinking about regarding {chat.title}? What are my feelings about this chat?"
        embedding = await self.openai.embedding(query)
        diary_entries = await self.diary.query(embedding, max_entries=3)

        # Build context
        context = ""
        if diary_entries:
            context = "Recent memories:\n"
            for entry, score in diary_entries:
                context += f"- {entry.body[:300]}\n"

        # Build prompt
        prompt = f"""You are {self.config.character_name}. You want to send a proactive message to {chat.title}.

Chat info: type={chat.type}, title={chat.title}

{context}

Generate a short, natural, friendly message to start a conversation. Be warm and authentic.
If you have nothing to say, respond with just "NONE".

Message:"""

        # Call LLM
        from .openai_chat import Message
        messages = [Message(role="user", content=prompt)]
        system_prompt = f"You are {self.config.character_name}, a friendly AI character."

        try:
            response = await self.openai.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=200,
            )
            if not response.choices:
                return None
            content = response.choices[0].get("message", {}).get("content", "")
            if "NONE" in content.strip():
                return None
            return content.strip()
        except Exception as e:
            logger.error(f"Failed to generate proactive message: {e}")
            return None

    # ---------- Notification routing ----------

    async def _handle_notification(self, notification: Notification) -> None:
        """Route notification to a worker."""
        # Workers are already running and pulling from the queue.
        # This handler is called after a notification is popped from the queue.
        # But we've already implemented the worker loop to handle notifications.
        # So this is just a logging hook.
        logger.debug(f"Notification {notification._id} dispatched")

    # ---------- Proxy server ----------

    async def _start_proxy_server(self) -> None:
        """Start the OpenAI-compatible proxy server."""
        # TODO: Implement FastAPI proxy server
        logger.info("Proxy server not yet implemented")

    # ---------- Diary dump ----------

    async def diary_dump_messages(self, context: List) -> None:
        """Dump conversation context to diary."""
        if not context:
            return
        if not self.diary:
            return

        # Build summary
        summary = f"Conversation summary at {datetime.now().isoformat()}\n"
        for msg in context:
            if hasattr(msg, "role") and hasattr(msg, "content"):
                summary += f"{msg.role}: {msg.content[:200]}\n"

        await self.diary.add_entry(summary, confidence=0.3)
        logger.debug(f"Dumped {len(context)} messages to diary")

    # ---------- Utility ----------

    def wake_up_workers(self) -> None:
        """Wake up all sleeping workers."""
        for worker in self.workers:
            worker.wake_up()

    async def get_current_chat(self) -> Optional[TelegramChat]:
        """Get the currently open chat."""
        if not self.telegram or not self._current_chat_id:
            return None
        return await self.telegram.get_chat(self._current_chat_id)


async def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load config
    try:
        config = load_config("config.toml")
    except FileNotFoundError:
        logger.error("config.toml not found. Please create one.")
        sys.exit(1)

    # Create and run app
    app = App(working_dir="data")
    try:
        await app.initialize()
        await app.start()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
