"""Persist working memory context to disk (Phase 3).

Saves and loads WorkingMemoryContext as a structured markdown file,
so state survives application restarts.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkingMemoryFileStore:
    """Persist working memory to working_memory.md.

    Format:
        # Working Memory
        ## user_id / chat_id
        - topic: ...
        - summary: ...
        - promises: [...]
        - plans: [...]
        - questions: [...]
        - last_interaction: ISO timestamp
        - emotion: ...
    """

    def __init__(self, file_path: Path | str):
        """Initialize file store.

        Args:
            file_path: Path to working memory file
        """
        self._file_path = Path(file_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path:
        return self._file_path

    def save_all(self, contexts: dict[tuple[str, str], Any]) -> None:
        """Save all working memory contexts to file.

        Args:
            contexts: Dict of (user_id, chat_id) → WorkingMemoryContext
        """
        if not contexts:
            return

        lines = [
            "# Working Memory",
            f"_Last saved: {datetime.now(UTC).isoformat()}_",
            "",
        ]

        for (user_id, chat_id), ctx in contexts.items():
            lines.append(f"## {user_id} / {chat_id}")
            lines.append(f"- **channel**: {ctx.channel}")
            lines.append(f"- **topic**: {ctx.current_topic or '(none)'}")
            lines.append(f"- **summary**: {ctx.conversation_summary or '(none)'}")
            lines.append(f"- **last_interaction**: {ctx.last_interaction}")
            lines.append(f"- **emotion**: {ctx.emotion_state or '(none)'}")

            if ctx.pending_questions:
                lines.append("- **pending_questions**:")
                for q in ctx.pending_questions:
                    lines.append(f"  - {q}")

            if ctx.promises:
                lines.append("- **promises**:")
                for p in ctx.promises:
                    if isinstance(p, dict):
                        desc = p.get("description", str(p))
                        fulfilled = p.get("fulfilled", False)
                        lines.append(f"  - {'[x]' if fulfilled else '[ ]'} {desc}")
                    else:
                        lines.append(f"  - {p}")

            if ctx.plans:
                lines.append("- **plans**:")
                for plan in ctx.plans:
                    lines.append(f"  - {json.dumps(plan, ensure_ascii=False)}")

            if ctx.metadata:
                lines.append(f"- **metadata**: {json.dumps(ctx.metadata, ensure_ascii=False)}")

            lines.append("")

        try:
            self._file_path.write_text("\n".join(lines), encoding="utf-8")
            logger.debug(f"Saved {len(contexts)} working memory contexts to {self._file_path}")
        except OSError as e:
            logger.error(f"Failed to save working memory: {e}")

    def save(self, context: Any) -> None:
        """Save a single working memory context (appends/updates).

        For simplicity, this is a no-op in favor of save_all() which
        writes the entire dict atomically. Use save_all() from
        WorkingMemory.save_to_file().
        """
        # This method is kept as interface placeholder.
        # WorkingMemory.save_to_file() calls save_all() with the full dict.

    def load_all(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Load all working memory contexts from file.

        Returns:
            Dict of (user_id, chat_id) → context data dict.
            Returns empty dict if file doesn't exist or can't be parsed.
        """
        if not self._file_path.exists():
            logger.debug("No working memory file found")
            return {}

        try:
            content = self._file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to read working memory: {e}")
            return {}

        return self._parse_markdown(content)

    def _parse_markdown(self, content: str) -> dict[tuple[str, str], dict[str, Any]]:
        """Parse working memory markdown into structured data.

        Args:
            content: File content

        Returns:
            Parsed contexts dict
        """
        contexts: dict[tuple[str, str], dict[str, Any]] = {}
        current_key: tuple[str, str] | None = None
        current_data: dict[str, Any] = {}

        for line in content.split("\n"):
            line = line.rstrip()

            # Section header: ## user_id / chat_id
            if line.startswith("## "):
                # Save previous section
                if current_key:
                    contexts[current_key] = current_data

                parts = line[3:].split(" / ", 1)
                if len(parts) == 2:
                    current_key = (parts[0].strip(), parts[1].strip())
                    current_data = {
                        "channel": "telegram",
                        "current_topic": None,
                        "conversation_summary": None,
                        "pending_questions": [],
                        "promises": [],
                        "plans": [],
                        "last_interaction": None,
                        "emotion_state": None,
                        "metadata": {},
                    }
                else:
                    current_key = None
                continue

            if not current_key:
                continue

            # Parse key-value fields
            if line.startswith("- **") and "**:" in line:
                key_part, _, value = line[4:].partition("**:")
                key = key_part.strip()
                value = value.strip()

                if key == "channel":
                    current_data["channel"] = value
                elif key == "topic":
                    current_data["current_topic"] = value if value != "(none)" else None
                elif key == "summary":
                    current_data["conversation_summary"] = value if value != "(none)" else None
                elif key == "last_interaction":
                    current_data["last_interaction"] = value
                elif key == "emotion":
                    current_data["emotion_state"] = value if value != "(none)" else None
                elif key == "metadata":
                    try:
                        current_data["metadata"] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass

        # Save last section
        if current_key:
            contexts[current_key] = current_data

        return contexts

    def load_contexts(self) -> list[Any]:
        """Load all working memory contexts as typed WorkingMemoryContext objects.

        Returns:
            List of WorkingMemoryContext instances reconstructed from file.
        """
        from ...interfaces.memory import WorkingMemoryContext

        raw = self.load_all()
        contexts = []
        for (user_id, chat_id), data in raw.items():
            last_interaction = data.get("last_interaction")
            if isinstance(last_interaction, str):
                try:
                    last_interaction = datetime.fromisoformat(last_interaction)
                except ValueError:
                    last_interaction = None

            contexts.append(WorkingMemoryContext(
                user_id=user_id,
                chat_id=chat_id,
                channel=data.get("channel", "telegram"),
                current_topic=data.get("current_topic"),
                conversation_summary=data.get("conversation_summary"),
                pending_questions=data.get("pending_questions", []),
                promises=data.get("promises", []),
                plans=data.get("plans", []),
                last_interaction=last_interaction,
                emotion_state=data.get("emotion_state"),
                metadata=data.get("metadata", {}),
            ))
        return contexts

    def render_for_prompt(self, context: Any) -> str:
        """Render a working memory context as prompt-friendly text.

        Args:
            context: WorkingMemoryContext instance

        Returns:
            Formatted string for injection into system prompt
        """
        lines = []

        if context.current_topic:
            lines.append(f"Current topic: {context.current_topic}")
        if context.conversation_summary:
            lines.append(f"Conversation summary: {context.conversation_summary}")
        if context.emotion_state:
            lines.append(f"Emotional state: {context.emotion_state}")

        if context.pending_questions:
            lines.append("Pending questions:")
            for q in context.pending_questions:
                lines.append(f"  - {q}")

        if context.promises:
            lines.append("Unfulfilled promises:")
            for p in context.promises:
                if isinstance(p, dict) and not p.get("fulfilled", True):
                    lines.append(f"  - {p.get('description', str(p))}")
                elif isinstance(p, str):
                    lines.append(f"  - {p}")

        if context.plans:
            lines.append("Active plans:")
            for plan in context.plans:
                if isinstance(plan, dict):
                    desc = plan.get("description", json.dumps(plan, ensure_ascii=False))
                    lines.append(f"  - {desc}")
                else:
                    lines.append(f"  - {plan}")

        return "\n".join(lines) if lines else ""
