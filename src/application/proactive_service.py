"""Proactive messaging service.

Handles autonomous proactive messages to users.
Extracted from app.py god object (ТЗ-001 punkt 5).
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta

from ..di import Dependencies

logger = logging.getLogger(__name__)


class ProactiveMessageService:
    """Handles proactive messaging.

    Responsibilities:
    1. Periodically check for proactive messaging opportunities
    2. Select appropriate chats
    3. Generate contextual messages
    4. Send messages autonomously

    Based on C++ kuni proactive behavior pattern.
    """

    def __init__(
        self,
        deps: Dependencies,
        check_interval_min: int = 30,
        check_interval_max: int = 60
    ):
        """Initialize proactive messaging service.

        Args:
            deps: Dependency injection container
            check_interval_min: Minimum check interval in minutes
            check_interval_max: Maximum check interval in minutes
        """
        self._deps = deps
        self._check_interval_min = check_interval_min
        self._check_interval_max = check_interval_max
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start proactive messaging loop."""
        if self._running:
            return

        if not self._deps.telegram_client:
            logger.info("Telegram disabled, proactive messaging unavailable")
            return

        self._running = True
        self._task = asyncio.create_task(self._proactive_loop(), name="proactive-messages")
        logger.info(f"Proactive messaging started (check interval: {self._check_interval_min}-{self._check_interval_max}m)")

    async def stop(self) -> None:
        """Stop proactive messaging loop."""
        if not self._running:
            return

        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Proactive messaging stopped")

    async def _proactive_loop(self) -> None:
        """Background loop for proactive messages.

        Implements "act proactively" feature from original kuni:
        - Periodically check pinned chats and important contacts
        - If enough time has passed, send a message
        - Use diary for context
        """
        logger.info("Proactive loop started")

        while self._running:
            try:
                # Wait for random interval
                interval = random.randint(
                    self._check_interval_min * 60,
                    self._check_interval_max * 60
                )
                await asyncio.sleep(interval)

                if not self._running:
                    break

                # Check if should act proactively
                if not self._should_act_proactively():
                    continue

                # Get candidate chats
                chats = await self._get_proactive_chats()
                if not chats:
                    continue

                # Pick random chat
                chat = random.choice(chats)

                # Generate and send message
                message = await self._generate_proactive_message(chat)
                if message:
                    await self._deps.telegram_client.send_message(chat.id, message)
                    logger.info(f"Proactive message sent to {chat.title} ({chat.id})")

            except asyncio.CancelledError:
                break
            except (ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.error(f"Error in proactive loop: {e}")
                await asyncio.sleep(60)  # Backoff on error

        logger.info("Proactive loop stopped")

    def _should_act_proactively(self) -> bool:
        """Determine if should act proactively now.

        Returns:
            True if should send proactive message (15% chance)
        """
        # Random chance: 15% per check (~1-2 times per day)
        return random.random() <= 0.15

    async def _get_proactive_chats(self) -> list:
        """Get candidate chats for proactive messages.

        Prioritizes:
        1. Pinned chats
        2. Chats with papik (owner)
        3. Recent activity (but not too recent)
        4. Respect can_write_to_a_new_person setting

        Returns:
            List of candidate chats (top 10)
        """
        all_chats = await self._deps.telegram_client.get_chats(limit=100)
        candidates = []

        for chat in all_chats:
            # Skip channels
            if chat.type == "channel":
                continue

            # Skip if not a member
            if not chat.is_member:
                continue

            # Skip empty chats
            if not chat.last_message:
                continue

            # Check last message timing
            if not await self._is_good_timing(chat):
                continue

            # Check if we've talked to this person before
            if not await self._can_write_to_chat(chat):
                continue

            candidates.append(chat)

        # Sort by priority
        candidates.sort(key=self._chat_priority, reverse=True)
        return candidates[:10]

    async def _is_good_timing(self, chat) -> bool:
        """Check if timing is good for proactive message.

        Args:
            chat: Chat to check

        Returns:
            True if good timing
        """
        if not chat.last_message:
            return False

        last_date = datetime.fromtimestamp(chat.last_message.date, tz=self._config.timezone_info)
        now = datetime.now(self._config.timezone_info)
        time_since = now - last_date

        # If last message was from us
        if chat.last_message.is_outgoing:
            # Don't message again if we messaged < 2h ago
            return time_since >= timedelta(hours=2)
        else:
            # If they messaged us < 30min ago, we might still be in conversation
            return time_since >= timedelta(minutes=30)

    async def _can_write_to_chat(self, chat) -> bool:
        """Check if can write to chat based on settings.

        Args:
            chat: Chat to check

        Returns:
            True if allowed to write
        """
        # If can_write_to_a_new_person is false, check if we've talked before
        if not self._deps.config.can_write_to_a_new_person and chat.type == "private":
            history = await self._deps.telegram_client.get_chat_history(chat.id, limit=20)
            # Check if we've ever sent a message
            if not any(m.is_outgoing for m in history):
                return False

        return True

    def _chat_priority(self, chat) -> tuple:
        """Calculate chat priority for proactive messaging.

        Args:
            chat: Chat

        Returns:
            (priority_score, message_age)
        """
        priority = 0

        # Pinned chats have high priority
        if chat.is_pinned:
            priority += 100

        # Owner's chat has elevated priority
        if chat.id == self._deps.config.papik_chat_id:
            priority += 50

        # Calculate message age (prefer chats we haven't talked to in a while)
        age = 0
        if chat.last_message:
            age = int((datetime.now(self._config.timezone_info) - datetime.fromtimestamp(chat.last_message.date, tz=self._config.timezone_info)).total_seconds())

        return (priority, age)

    async def _generate_proactive_message(self, chat) -> str | None:
        """Generate proactive message using LLM and diary context.

        Args:
            chat: Target chat

        Returns:
            Generated message or None
        """
        if not self._deps.openai_chat or not self._deps.diary:
            return None

        # Query diary for context
        query = f"What have I been thinking about regarding {chat.title}? What are my feelings about this chat?"
        embedding = await self._deps.openai_chat.embedding(query)
        diary_entries = await self._deps.diary.query(embedding, max_entries=3)

        # Build context from diary
        context = ""
        if diary_entries:
            context = "Recent memories:\n"
            for entry, score in diary_entries:
                context += f"- {entry.body[:300]}\n"

        # Build prompt
        prompt = f"""You are {self._deps.config.character_name}. You want to send a proactive message to {chat.title}.

Chat info: type={chat.type}, title={chat.title}

{context}

Generate a short, natural, friendly message to start a conversation. Be warm and authentic.
If you have nothing to say, respond with just "NONE".

Message:"""

        # Call LLM
        from ..openai_chat import Message
        messages = [Message(role="user", content=prompt)]
        system_prompt = f"You are {self._deps.config.character_name}, a friendly AI character."

        try:
            response = await self._deps.openai_chat.chat(
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

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Failed to generate proactive message: {e}")
            return None
