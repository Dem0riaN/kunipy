"""Memory formation - automatic memory piece creation from conversations (ТЗ-002 пункт 31).

Extracts important facts, events, thoughts, and relationships from conversation messages.
Uses LLM to determine what should become long-term memory.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from ...config import Config
from ...domain.memory_models import ConversationMessage
from ...interfaces.llm import IOpenAIChat
from ...interfaces.memory import MemoryKind, MemoryPiece, MemoryScope

logger = logging.getLogger(__name__)


MEMORY_EXTRACTION_PROMPT = """Analyze the following conversation and extract information that should be stored in long-term memory.

Extract:
1. **Facts** - concrete information about people, places, things
2. **Events** - things that happened
3. **Thoughts/Reflections** - opinions, feelings, reflections by the character
4. **Entity Descriptions** - descriptions of people, objects, concepts
5. **Relationships** - connections between entities

For each memory piece, provide:
- kind: one of [fact, event, thought, entity_description, other]
- content: concise summary (1-3 sentences)
- importance: 0.0 to 1.0 (how important to remember)
- confidence: -1.0 to 1.0 (-1=lie, 0=uncertain, 1=confirmed fact)
- scope: one of [private, user, chat, shared, global]
- entities: list of named entities mentioned

Return JSON array of memory pieces. If nothing important, return empty array.

Conversation:
{conversation}

Return only valid JSON array, no explanation:"""


class MemoryFormationService:
    """Service for automatic memory piece creation from conversations.

    Uses LLM to extract important information that should be remembered.
    """

    def __init__(
        self,
        llm_client: IOpenAIChat,
        config: Config,
    ):
        """Initialize memory formation service.

        Args:
            llm_client: LLM client for extraction
            config: Application configuration
        """
        self.llm_client = llm_client
        self.config = config

    async def extract_memories_from_conversation(
        self,
        messages: list[ConversationMessage],
        user_id: str,
        chat_id: str,
        channel: str,
    ) -> list[MemoryPiece]:
        """Extract memory pieces from conversation messages.

        Args:
            messages: Conversation messages to analyze
            user_id: User ID
            chat_id: Chat ID
            channel: Channel

        Returns:
            List of extracted memory pieces
        """
        if not messages:
            return []

        # Format conversation for LLM
        conversation_text = self._format_conversation(messages)

        # Call LLM to extract memories
        try:
            extracted = await self._call_llm_extraction(conversation_text)
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return []

        # Convert to MemoryPiece objects
        memory_pieces = []
        for item in extracted:
            try:
                piece = self._create_memory_piece(
                    item=item,
                    user_id=user_id,
                    chat_id=chat_id,
                    channel=channel,
                    source_messages=messages,
                )
                memory_pieces.append(piece)
            except Exception as e:
                logger.warning(f"Failed to create memory piece: {e}")
                continue

        logger.info(f"Extracted {len(memory_pieces)} memory pieces from {len(messages)} messages")
        return memory_pieces

    async def extract_from_single_message(
        self,
        message: ConversationMessage,
    ) -> list[MemoryPiece]:
        """Quick extraction from single important message.

        Args:
            message: Single message to analyze

        Returns:
            List of extracted memory pieces
        """
        return await self.extract_memories_from_conversation(
            messages=[message],
            user_id=message.user_id,
            chat_id=message.chat_id,
            channel=message.channel,
        )

    def _format_conversation(self, messages: list[ConversationMessage]) -> str:
        """Format conversation messages for LLM.

        Args:
            messages: Messages to format

        Returns:
            Formatted conversation text
        """
        lines = []
        for msg in messages:
            timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M")
            role_label = "User" if msg.role == "user" else "Assistant"
            lines.append(f"[{timestamp}] {role_label}: {msg.content}")

        return "\n".join(lines)

    async def _call_llm_extraction(self, conversation_text: str) -> list[dict]:
        """Call LLM to extract memories from conversation.

        Args:
            conversation_text: Formatted conversation

        Returns:
            List of extracted memory items (raw dicts)
        """
        prompt = MEMORY_EXTRACTION_PROMPT.format(conversation=conversation_text)

        # Build message list
        from ...openai_chat import Message

        messages = [Message(role="user", content=prompt)]

        response = await self.llm_client.chat(
            messages=messages,
            system_prompt="You are a memory extraction assistant. Extract important information from conversations and return it as JSON.",
            temperature=0.3,  # Lower temperature for more consistent extraction
        )

        # Parse JSON response - response.choices is a list of dicts
        choice = response.choices[0]
        # For dict format: choice['message']['content']
        if isinstance(choice, dict):
            content = choice.get("message", {}).get("content", "").strip()
        else:
            # For object format
            content = choice.message.content.strip()

        # Remove markdown code blocks if present
        content = content.removeprefix("```json")
        content = content.removeprefix("```")
        content = content.removesuffix("```")
        content = content.strip()

        try:
            extracted = json.loads(content)
            if not isinstance(extracted, list):
                logger.warning(f"LLM returned non-list: {type(extracted)}")
                return []
            return extracted
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {content}")
            return []

    def _create_memory_piece(
        self,
        item: dict,
        user_id: str,
        chat_id: str,
        channel: str,
        source_messages: list[ConversationMessage],
    ) -> MemoryPiece:
        """Create MemoryPiece from extracted item.

        Args:
            item: Extracted memory item (dict from LLM)
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            source_messages: Source conversation messages

        Returns:
            MemoryPiece object
        """
        # Parse kind
        kind_str = item.get("kind", "other").lower()
        kind_map = {
            "fact": MemoryKind.FACT,
            "event": MemoryKind.EVENT,
            "thought": MemoryKind.THOUGHT,
            "entity_description": MemoryKind.ENTITY_DESCRIPTION,
            "other": MemoryKind.OTHER,
        }
        kind = kind_map.get(kind_str, MemoryKind.OTHER)

        # Parse scope
        scope_str = item.get("scope", "user").lower()
        scope_map = {
            "private": MemoryScope.PRIVATE,
            "user": MemoryScope.USER,
            "chat": MemoryScope.CHAT,
            "shared": MemoryScope.SHARED,
            "global": MemoryScope.GLOBAL,
        }
        scope = scope_map.get(scope_str, MemoryScope.USER)

        # Extract values
        content = item.get("content", "")
        importance = float(item.get("importance", 0.5))
        confidence = float(item.get("confidence", 0.0))
        entities = item.get("entities", [])

        # Clamp values
        importance = max(0.0, min(1.0, importance))
        confidence = max(-1.0, min(1.0, confidence))

        # Determine user_id/chat_id based on scope
        scope_user_id = user_id if scope in [MemoryScope.USER, MemoryScope.CHAT] else None
        scope_chat_id = chat_id if scope == MemoryScope.CHAT else None

        # Create memory piece
        now = datetime.now(UTC)
        piece = MemoryPiece(
            id=str(uuid.uuid4()),
            kind=kind,
            content=content,
            confidence=confidence,
            importance=importance,
            scope=scope,
            user_id=scope_user_id,
            chat_id=scope_chat_id,
            channel=channel,
            embedding=[],  # Will be generated later
            source_type="conversation",
            source_message_ids=[msg.message_id for msg in source_messages],
            created_at=now,
            updated_at=now,
            last_used=now,
            usage_count=0,
            retrieval_cues=[],
            entities=entities if isinstance(entities, list) else [],
            metadata={
                "extracted_by": "llm",
                "extraction_timestamp": now.isoformat(),
            },
        )

        return piece
