"""Conversation-to-diary pipeline service (Phase 3).

Auto-dumps conversation context to diary when token count exceeds threshold.
Uses prompts/diary_save.md (currently orphan) for LLM summarization.
New entries get Unix timestamp IDs (замечание 3).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...config import Config
    from ...diary import Diary
    from ...openai_chat import OpenAIChat
    from .token_counter import TokenCounter

logger = logging.getLogger(__name__)


class DiaryDumpService:
    """Auto-dump conversation to diary when context exceeds token threshold.

    Fills critical gap: worker.py:311 currently trims history without saving.
    This service:
    1. Checks token count before trimming
    2. If threshold exceeded: LLM summarization via prompts/diary_save.md
    3. Saves structured diary entries (not raw dumps)
    """

    def __init__(
        self,
        diary: Diary,
        openai_chat: OpenAIChat,
        config: Config,
        token_counter: TokenCounter,
        prompts_dir: str | Path = "prompts",
    ):
        """Initialize diary dump service.

        Args:
            diary: Diary instance for saving entries
            openai_chat: LLM client for summarization
            config: Application configuration
            token_counter: Token counter for threshold checks
            prompts_dir: Directory containing prompt templates
        """
        self._diary = diary
        self._openai = openai_chat
        self._config = config
        self._counter = token_counter
        self._prompts_dir = Path(prompts_dir)

        # Load diary_save.md prompt
        self._diary_save_prompt = self._load_prompt("diary_save.md")

        # Track last dump time per chat to avoid spam
        self._last_dump_time: dict[int, float] = {}
        self._min_dump_interval = 300  # 5 minutes minimum between dumps

    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file.

        Args:
            filename: Prompt file name

        Returns:
            Prompt text or empty string if not found
        """
        prompt_path = self._prompts_dir / filename
        if not prompt_path.exists():
            logger.warning(f"Prompt file not found: {prompt_path}")
            return ""

        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load prompt {filename}: {e}")
            return ""

    async def maybe_dump(
        self,
        messages: list[Any],
        chat_id: int,
    ) -> list[Any]:
        """Check token count and dump to diary if threshold exceeded.

        Called BEFORE history trimming in worker.py.

        Args:
            messages: Current conversation history
            chat_id: Chat identifier

        Returns:
            Trimmed message list (or original if no dump needed)
        """
        token_count = self._counter.count_messages(messages)
        threshold = self._config.diary_context_token_threshold

        if token_count <= threshold:
            # Below threshold, no dump needed
            return messages

        # Check cooldown
        now = time.time()
        last_dump = self._last_dump_time.get(chat_id, 0)
        if now - last_dump < self._min_dump_interval:
            logger.debug(f"Dump cooldown active for chat {chat_id}")
            return messages

        logger.info(
            f"Token count {token_count} exceeds threshold {threshold} "
            f"for chat {chat_id}, dumping to diary"
        )

        try:
            # Summarize and save to diary
            entries = await self._summarize_for_diary(messages)
            for entry_text in entries:
                await self._diary.add_entry(
                    text=entry_text,
                    confidence=0.7,
                    visibility="chat",
                    chat_id=str(chat_id),
                    source_channel="telegram",
                )

            # Update last dump time
            self._last_dump_time[chat_id] = now

            # Trim history to keep recent context (matches original trim
            # behavior: keep last 15 messages)
            keep_count = 15
            if len(messages) > keep_count:
                trimmed = messages[-keep_count:]
                logger.info(f"Trimmed history from {len(messages)} to {len(trimmed)} messages")
                return trimmed

        except Exception as e:
            logger.exception(f"Failed to dump conversation to diary: {e}")

        return messages

    async def _summarize_for_diary(self, messages: list[Any]) -> list[str]:
        """Summarize conversation using LLM and diary_save.md prompt.

        Args:
            messages: Conversation history to summarize

        Returns:
            List of diary entry texts (split by --- separators)
        """
        if not self._diary_save_prompt:
            logger.warning("diary_save.md prompt not available, skipping dump")
            return []

        # Format conversation for summarization
        conversation_text = self._format_conversation(messages)

        # Build user message for summarization
        user_content = (
            f"Please summarize the following conversation into diary entries:\n\n"
            f"{conversation_text}"
        )
        from ...openai_chat import Message as ChatMessage
        user_msg = ChatMessage(role="user", content=user_content)

        # Send to LLM
        try:
            response = await self._openai.chat(
                messages=[user_msg],
                system_prompt=self._diary_save_prompt,
                temperature=0.7,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error(f"LLM call failed during diary dump: {e}")
            return []

        if not response.choices:
            return []

        # Extract text from response
        choice = response.choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")

        if not content:
            return []

        # Split by --- separator lines (as specified in diary_save.md).
        # Only lines that are exactly "---" divide pieces, so bodies may
        # contain inline dashes without being split incorrectly.
        entries = [
            entry.strip()
            for entry in re.split(r"^---$", content, flags=re.MULTILINE)
            if entry.strip()
        ]

        logger.info(f"Generated {len(entries)} diary entries from conversation")
        return entries

    def _format_conversation(self, messages: list[Any]) -> str:
        """Format message list into readable conversation text.

        Args:
            messages: List of Message objects or dicts

        Returns:
            Formatted conversation string
        """
        lines = []
        for msg in messages:
            role = self._get_role(msg)
            content = self._get_content(msg)

            if role and content:
                lines.append(f"{role}: {content}")

        return "\n\n".join(lines)

    def _get_role(self, msg: Any) -> str:
        """Extract role from message."""
        if isinstance(msg, dict):
            return msg.get("role", "")
        return getattr(msg, "role", "")

    def _get_content(self, msg: Any) -> str:
        """Extract text content from message."""
        if isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = getattr(msg, "content", "")

        # Handle multimodal content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            return " ".join(text_parts)

        return str(content) if content else ""

    async def dump_on_shutdown(
        self,
        all_chats: dict[int, list[Any]],
    ) -> int:
        """Dump all active conversations on graceful shutdown.

        Better replacement for app.py raw dump (line ~229).
        Uses LLM summarization instead of raw truncation.

        Args:
            all_chats: Dict mapping chat_id to message list

        Returns:
            Number of diary entries created
        """
        total_entries = 0

        for chat_id, messages in all_chats.items():
            if not messages:
                continue

            try:
                entries = await self._summarize_for_diary(messages)
                for entry_text in entries:
                    await self._diary.add_entry(
                        text=entry_text,
                        confidence=0.5,  # Lower confidence for shutdown dumps
                        visibility="chat",
                        chat_id=str(chat_id),
                        source_channel="telegram",
                    )
                    total_entries += 1

            except Exception as e:
                logger.error(f"Failed to dump chat {chat_id} on shutdown: {e}")

        logger.info(f"Shutdown dump: {total_entries} diary entries created")
        return total_entries
