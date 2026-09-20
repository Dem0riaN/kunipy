"""Diary context injection for auto-RAG (Phase 4).

Injects relevant diary entries into system prompt (<related_memories>)
and user messages (<your_diary_page>) following C++ kuni behavior.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ...config import Config
    from ...diary import Diary
    from ...openai_chat import OpenAIChat

logger = logging.getLogger(__name__)


class DiaryContextInjector:
    """Auto-inject relevant diary entries into conversation context.

    Two injection mechanisms (both from original C++ kuni):
    1. System prompt: <related_memories> — summary/teaser via diary.query()
    2. User messages: <your_diary_page> — full-text entries (top-N)

    Controlled by config.diary_auto_rag_enabled (default True).
    """

    def __init__(
        self,
        diary: Diary,
        openai_chat: OpenAIChat,
        config: Config,
        max_system_entries: int = 5,
        max_message_entries: int = 3,
    ):
        """Initialize diary context injector.

        Args:
            diary: Diary instance for querying entries
            openai_chat: LLM client for embedding queries
            config: Application configuration
            max_system_entries: Max entries for system prompt <related_memories>
            max_message_entries: Max entries for user message <your_diary_page>
        """
        self._diary = diary
        self._openai = openai_chat
        self._config = config
        self._max_system_entries = max_system_entries
        self._max_message_entries = max_message_entries

    async def inject_into_system_prompt(self, query_text: str) -> str:
        """Query diary and format as <related_memories> for system prompt.

        Args:
            query_text: User's message to query diary with

        Returns:
            Formatted <related_memories> block (empty string if no entries)
        """
        if not query_text.strip():
            return ""

        # Get embedding for query
        try:
            query_embedding = await self._get_embedding(query_text)
        except Exception as e:
            logger.error(f"Failed to get embedding for diary query: {e}")
            return ""

        # Query diary
        try:
            results = await self._diary.query(
                query_vector=query_embedding,
                max_entries=self._max_system_entries,
            )
        except Exception as e:
            logger.error(f"Failed to query diary for system prompt: {e}")
            return ""

        if not results:
            return ""

        # Format as <related_memories>
        lines = []
        for i, (entry, score) in enumerate(results, 1):
            # Teaser: first 150 chars of body
            body_preview = entry.body[:150].replace("\n", " ").strip()
            if len(entry.body) > 150:
                body_preview += "..."

            conf = entry.metadata.get("confidence", 0.0)
            kind = entry.metadata.get("kind", "other")

            lines.append(f"{i}. [{kind}] {body_preview}")
            if conf != 0.0:
                lines.append(f"   (confidence: {conf:+.2f})")

        return "\n".join(lines)

    async def inject_into_messages(
        self,
        messages: list[Any],
        user_query: str,
    ) -> list[Any]:
        """Query diary and inject full-text entries as <your_diary_page>.

        Injects BEFORE the last user message (so LLM sees it as context).

        Args:
            messages: Current conversation message list
            user_query: User's message to query diary with

        Returns:
            Message list with <your_diary_page> injected (or original if no entries)
        """
        if not user_query.strip():
            return messages

        # Get embedding for query
        try:
            query_embedding = await self._get_embedding(user_query)
        except Exception as e:
            logger.error(f"Failed to get embedding for diary query: {e}")
            return messages

        # Query diary
        try:
            results = await self._diary.query(
                query_vector=query_embedding,
                max_entries=self._max_message_entries,
            )
        except Exception as e:
            logger.error(f"Failed to query diary for messages: {e}")
            return messages

        if not results:
            return messages

        # Format as <your_diary_page>
        diary_page = self.format_diary_page(results)

        # Find last user message index
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            # No user message found, append at end
            return messages

        # Inject before last user message
        from ...openai_chat import Message

        diary_msg = Message(role="user", content=diary_page)
        new_messages = (
            messages[:last_user_idx]
            + [diary_msg]
            + messages[last_user_idx:]
        )

        return new_messages

    @staticmethod
    def format_diary_page(
        results: list[tuple[Any, float]],
    ) -> str:
        """Format diary entries as <your_diary_page> block.

        Args:
            results: List of (DiaryEntry, score) tuples from diary.query()

        Returns:
            Formatted <your_diary_page> string
        """
        if not results:
            return ""

        lines = ["<your_diary_page>"]

        for entry, score in results:
            # Full body text
            lines.append(entry.body.strip())
            lines.append("\n---\n")

        # Remove trailing separator
        if lines and lines[-1] == "\n---\n":
            lines.pop()

        lines.append("</your_diary_page>")

        return "\n".join(lines)

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for text.

        Args:
            text: Input text to embed

        Returns:
            Embedding as numpy array
        """
        result = await self._openai.embedding(text)
        if hasattr(result, "tolist"):
            return np.array(result, dtype=np.float64)
        return np.array(result, dtype=np.float64)
