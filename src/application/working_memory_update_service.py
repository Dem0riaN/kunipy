"""Working memory update service (autonomy restoration).

Extracts working memory (promises, tasks, emotional state) from conversation
using LLM and prompts/important_things_to_remember.md prompt.
Bridges the gap between existing infrastructure and lifecycle integration.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import Config
    from ..interfaces import IOpenAIChat, IWorkingMemory

logger = logging.getLogger(__name__)


class WorkingMemoryUpdateService:
    """Service for extracting and updating working memory from conversations.

    Based on C++ kuni's important_things_to_remember functionality.
    Uses LLM to extract:
    - Emotional state
    - Physical state (fatigue)
    - Promises made
    - Tasks to complete
    - Pending questions
    """

    def __init__(
        self,
        working_memory: IWorkingMemory,
        openai_chat: IOpenAIChat,
        config: Config,
        prompts_dir: str | Path = "prompts",
        min_update_interval: float = 300.0,  # 5 minutes between updates
    ):
        """Initialize working memory update service.

        Args:
            working_memory: Working memory storage interface
            openai_chat: LLM client for extraction
            config: Application configuration
            prompts_dir: Directory containing prompt templates
            min_update_interval: Minimum seconds between updates per chat
        """
        self._working_memory = working_memory
        self._openai = openai_chat
        self._config = config
        self._prompts_dir = Path(prompts_dir)
        self._min_update_interval = min_update_interval

        # Load important_things_to_remember.md prompt
        self._prompt_template = self._load_prompt("important_things_to_remember.md")

        # Track last update time per chat
        self._last_update_time: dict[str, float] = {}

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

    async def update_after_session(
        self,
        messages: list[Any],
        user_id: str,
        chat_id: str,
        channel: str = "telegram",
    ) -> str | None:
        """Extract working memory from conversation and update storage.

        Called after conversation session ends (before sleep or context clear).

        Args:
            messages: Conversation history
            user_id: User identifier
            chat_id: Chat identifier
            channel: Communication channel

        Returns:
            Updated working memory text, or None if update skipped/failed
        """
        if not self._prompt_template:
            logger.warning("important_things_to_remember prompt not available")
            return None

        # Check cooldown
        now = time.time()
        last_update = self._last_update_time.get(chat_id, 0)
        if now - last_update < self._min_update_interval:
            logger.debug(f"Update cooldown active for chat {chat_id}")
            return None

        if not messages:
            return None

        try:
            # Get current working memory context
            current_context = await self._working_memory.get_context(user_id, chat_id)
            previous_wm_text = self._format_working_memory_context(current_context)

            # Format conversation for extraction
            conversation_text = self._format_conversation(messages)

            # Build user message with variables substituted
            from ..prompt_loader import _substitute_prompt_vars

            timespan = "последние несколько часов"  # TODO: calculate from timestamps

            prompt_with_vars = _substitute_prompt_vars(
                self._prompt_template,
                self._config,  # Config object for CHARACTER_NAME, PAPIK_NAME, etc.
                timespan=timespan,
                previous_working_memory=previous_wm_text or "(пусто)",
            )

            user_content = (
                f"{prompt_with_vars}\n\n"
                f"**Диалог для анализа:**\n\n"
                f"{conversation_text}"
            )

            # Import Message here to avoid circular imports
            from ..openai_chat import Message as ChatMessage

            user_msg = ChatMessage(role="user", content=user_content)

            # Send to LLM
            response = await self._openai.chat(
                messages=[user_msg],
                temperature=0.7,
                max_tokens=1500,
            )

            if not response.choices:
                logger.warning("LLM returned no choices for working memory extraction")
                return None

            # Extract text from response
            choice = response.choices[0]
            message = choice.get("message", {})
            extracted_text = message.get("content", "")

            if not extracted_text or not extracted_text.strip():
                logger.warning("LLM returned empty working memory")
                return None

            # Parse extracted sections and update working memory
            parsed = self._parse_extracted_memory(extracted_text)

            # Update working memory storage
            await self._working_memory.update_context(
                user_id=user_id,
                chat_id=chat_id,
                updates={
                    "emotion_state": parsed.get("emotional_state"),
                    "conversation_summary": parsed.get("context"),
                    "pending_questions": parsed.get("pending_questions", []),
                    "promises": parsed.get("promises", []),
                    "metadata": {
                        "physical_state": parsed.get("physical_state"),
                        "tasks": parsed.get("tasks", []),
                        "last_update": now,
                    },
                },
            )

            # Update cooldown timer
            self._last_update_time[chat_id] = now

            logger.info(f"Updated working memory for chat {chat_id}")
            return extracted_text

        except Exception:
            logger.exception("Failed to extract/update working memory")
            return None

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
                # Translate role names to Russian for better context
                role_name = {
                    "user": "Пользователь",
                    "assistant": "Ассистент",
                    "system": "Система",
                }.get(role, role)
                lines.append(f"{role_name}: {content}")

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

    def _format_working_memory_context(self, context: Any) -> str:
        """Format WorkingMemoryContext into readable text.

        Args:
            context: WorkingMemoryContext object

        Returns:
            Formatted text or empty string
        """
        if not context:
            return ""

        parts = []

        if context.emotion_state:
            parts.append(f"Эмоциональное состояние: {context.emotion_state}")

        if context.current_topic:
            parts.append(f"Текущая тема: {context.current_topic}")

        if context.promises:
            promises_text = "\n".join(
                f"- {p.get('text', p)}" if isinstance(p, dict) else f"- {p}"
                for p in context.promises
            )
            parts.append(f"Обещания:\n{promises_text}")

        if context.pending_questions:
            questions_text = "\n".join(f"- {q}" for q in context.pending_questions)
            parts.append(f"Отложенные вопросы:\n{questions_text}")

        if context.metadata and context.metadata.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in context.metadata["tasks"])
            parts.append(f"Задачи:\n{tasks_text}")

        return "\n\n".join(parts) if parts else ""

    def _parse_extracted_memory(self, text: str) -> dict[str, Any]:
        """Parse LLM output into structured sections.

        Args:
            text: LLM-generated working memory text

        Returns:
            Dict with parsed sections
        """
        result: dict[str, Any] = {}

        # Split by markdown headers
        sections = {}
        current_section = None
        current_lines = []

        for line in text.split("\n"):
            if line.startswith("## "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                # Start new section
                current_section = line[3:].strip()
                current_lines = []
            else:
                if current_section:
                    current_lines.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()

        # Map sections to result keys
        if "Эмоциональное состояние" in sections:
            result["emotional_state"] = sections["Эмоциональное состояние"]

        if "Физическое состояние" in sections:
            result["physical_state"] = sections["Физическое состояние"]

        if "Контекст" in sections:
            result["context"] = sections["Контекст"]

        # Parse list sections
        if "Обещания" in sections:
            promises_text = sections["Обещания"]
            if "Нет активных обещаний" not in promises_text:
                promises = [
                    line.strip("- ").strip()
                    for line in promises_text.split("\n")
                    if line.strip() and line.strip().startswith("-")
                ]
                result["promises"] = [{"text": p} for p in promises if p]
            else:
                result["promises"] = []

        if "Задачи" in sections:
            tasks_text = sections["Задачи"]
            if "Нет задач" not in tasks_text:
                tasks = [
                    line.strip("- ").strip()
                    for line in tasks_text.split("\n")
                    if line.strip() and line.strip().startswith("-")
                ]
                result["tasks"] = [t for t in tasks if t]
            else:
                result["tasks"] = []

        if "Отложенные вопросы" in sections:
            questions_text = sections["Отложенные вопросы"]
            if "Нет отложенных вопросов" not in questions_text:
                questions = [
                    line.strip("- ").strip()
                    for line in questions_text.split("\n")
                    if line.strip() and line.strip().startswith("-")
                ]
                result["pending_questions"] = [q for q in questions if q]
            else:
                result["pending_questions"] = []

        return result
