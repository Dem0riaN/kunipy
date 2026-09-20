"""Memory-integrated Worker with automatic memory formation (ТЗ-002 Этап 4).

Extension of base Worker that:
1. Retrieves memory context before generating response
2. Automatically creates memory pieces after interaction
3. Updates working memory state
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .domain.memory_models import ConversationMessage
from .infrastructure.memory.memory_formation import MemoryFormationService
from .notification_manager import Notification
from .worker import Worker

if TYPE_CHECKING:
    from .infrastructure.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)


class MemoryIntegratedWorker(Worker):
    """Worker with integrated memory system.

    Extends base Worker to:
    - Retrieve relevant memories before LLM call
    - Form new memories after successful interaction
    - Maintain working memory context
    """

    def __init__(
        self,
        memory_service: MemoryService | None = None,
        memory_formation: MemoryFormationService | None = None,
        **kwargs,
    ):
        """Initialize memory-integrated worker.

        Args:
            memory_service: Memory service for retrieval/storage
            memory_formation: Memory formation service
            **kwargs: Arguments for base Worker
        """
        super().__init__(**kwargs)
        self.memory_service = memory_service
        self.memory_formation = memory_formation
        self._last_retrieved_memories: dict[int, list] = {}

    async def _build_system_prompt(self, notification: Notification) -> str:
        """Build system prompt with memory context + legacy diary (override).

        Phase 4: Combines ТЗ-002 memory context with legacy diary auto-RAG.
        Both sources merged into diary_context slot (extension, not replacement).
        """
        from .character import build_system_prompt
        from .prompt_loader import _substitute_prompt_vars

        # Extract chat_id
        chat_id = self._extract_chat_id(notification)
        user_id = f"telegram:{chat_id}" if chat_id else "unknown"
        channel = "telegram"

        # Retrieve ТЗ-002 memory context
        memory_context_text = ""
        if self.memory_service and chat_id:
            try:
                memory_context_text = await self._retrieve_memory_context(
                    user_id=user_id,
                    chat_id=str(chat_id),
                    channel=channel,
                    query_text=notification.message,
                )
            except Exception as e:
                logger.error(f"Failed to retrieve memory context: {e}")

        # Format memories with variable substitution
        if memory_context_text:
            memory_context_text = _substitute_prompt_vars(memory_context_text, self.config)

        # Phase 4: retrieve legacy diary context (C++ format)
        legacy_diary = ""
        if self._diary_context_injector and self.config.diary_auto_rag_enabled:
            try:
                legacy_diary = await self._diary_context_injector.inject_into_system_prompt(
                    notification.message
                )
            except Exception as e:
                logger.error(f"Failed to inject legacy diary context: {e}")

        # Combine both sources (extension, not replacement)
        combined_diary = "\n".join(x for x in (memory_context_text, legacy_diary) if x)

        # Build base prompt with combined context
        base_prompt = build_system_prompt(
            config=self.config,
            working_memory_text=self._working_memory_context,
            diary_context=combined_diary,
        )

        return base_prompt

    async def _process_notification(self, notification: Notification) -> None:
        """Process notification with memory formation (override)."""
        chat_id = self._extract_chat_id(notification)

        # Store message in conversation history
        if self.memory_service and chat_id:
            user_id = f"telegram:{chat_id}"
            try:
                # Get message_id from metadata if available
                message_id = notification.metadata.get('message_id', 'unknown')

                await self.memory_service.store_message(
                    message_id=f"telegram:{message_id}",
                    user_id=user_id,
                    chat_id=str(chat_id),
                    channel="telegram",
                    role="user",
                    content=notification.message,
                    metadata=notification.metadata,
                )
            except Exception as e:
                logger.error(f"Failed to store user message: {e}")

        # Process notification normally (generate response)
        await super()._process_notification(notification)

        # After successful response, form memories
        if self.memory_service and self.memory_formation and chat_id:
            await self._form_memories_from_interaction(
                chat_id=chat_id,
                notification=notification,
            )

    async def _retrieve_memory_context(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        query_text: str,
    ) -> str:
        """Retrieve and format memory context for prompt.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            query_text: User's message

        Returns:
            Formatted memory context string
        """
        working_ctx, memories = await self.memory_service.retrieve_context(
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            query_text=query_text,
            max_pieces=10,
        )

        # Store for later use in memory formation
        self._last_retrieved_memories[int(chat_id)] = memories

        # Format memories for prompt
        if not memories:
            return ""

        lines = ["=== Relevant Memories ===\n"]

        for i, memory in enumerate(memories, 1):
            lines.append(f"{i}. [{memory.kind.value}] {memory.content}")
            if memory.confidence != 0.0:
                lines.append(f"   (confidence: {memory.confidence:+.2f})")

        lines.append("\n")

        # Add working memory context
        if working_ctx.promises:
            lines.append("=== Active Promises ===")
            for promise in working_ctx.promises:
                lines.append(f"- {promise['content']}")
            lines.append("")

        if working_ctx.plans:
            lines.append("=== Active Plans ===")
            for plan in working_ctx.plans:
                lines.append(f"- {plan['content']}")
            lines.append("")

        return "\n".join(lines)

    async def _form_memories_from_interaction(
        self,
        chat_id: int,
        notification: Notification,
    ) -> None:
        """Form new memory pieces from the interaction.

        Args:
            chat_id: Chat ID
            notification: Original notification
        """
        user_id = f"telegram:{chat_id}"

        # Get recent conversation history
        history = self.temporary_context.get(chat_id, [])
        if not history:
            return

        # Take last few exchanges for analysis
        recent_messages = history[-6:]  # Last 3 exchanges

        # Convert to ConversationMessage format
        conv_messages = []
        from datetime import UTC, datetime
        current_time = datetime.now(UTC)

        for msg in recent_messages:
            conv_messages.append(
                ConversationMessage(
                    message_id=f"temp:{len(conv_messages)}",
                    user_id=user_id,
                    chat_id=str(chat_id),
                    channel="telegram",
                    timestamp=current_time,
                    role=msg.role,
                    content=msg.content if isinstance(msg.content, str) else "",
                    metadata={},
                )
            )

        # Extract memories
        try:
            extracted_memories = await self.memory_formation.extract_memories_from_conversation(
                messages=conv_messages,
                user_id=user_id,
                chat_id=str(chat_id),
                channel="telegram",
            )

            logger.info(f"Extracted {len(extracted_memories)} memories from interaction")

            # Store memories with embeddings
            for memory in extracted_memories:
                # Generate embedding via MemoryService API
                memory.embedding = await self.memory_service.embed_text(memory.content)

                # Store in both ChromaDB (vectors) and SQLite (metadata)
                await self.memory_service.create_memory(memory)
                logger.debug(f"Stored memory: {memory.kind.value} - {memory.content[:50]}...")

        except Exception:
            logger.exception("Memory formation failed")

    def _extract_chat_id(self, notification: Notification) -> int | None:
        """Extract chat ID from notification.

        Args:
            notification: Notification object

        Returns:
            Chat ID or None
        """
        if notification.pin and notification.pin.startswith("chat_"):
            try:
                return int(notification.pin.split("_")[1])
            except (IndexError, ValueError):
                pass
        return None
