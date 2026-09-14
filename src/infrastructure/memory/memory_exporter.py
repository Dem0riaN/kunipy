"""Memory export tool - human-readable export (ТЗ-002 пункт 42, Этап 6).

Exports kunipy memory to human-readable formats without direct database access.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ...interfaces.memory import MemoryPiece, MemoryScope
from .memory_repository import MemoryRepository

logger = logging.getLogger(__name__)


class MemoryExporter:
    """Export memory to human-readable formats.

    Supports:
    - JSON export with full metadata
    - JSONL (line-delimited JSON) for streaming
    - Markdown export for human reading
    """

    def __init__(self, memory_repo: MemoryRepository):
        """Initialize exporter.

        Args:
            memory_repo: Memory repository to export from
        """
        self.memory_repo = memory_repo

    async def export_to_json(
        self,
        output_path: str | Path,
        scope: MemoryScope | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        include_embeddings: bool = False,
        pretty: bool = True,
    ) -> int:
        """Export memories to JSON file.

        Args:
            output_path: Output file path
            scope: Filter by scope (optional)
            user_id: Filter by user (optional)
            chat_id: Filter by chat (optional)
            include_embeddings: Include embedding vectors in output
            pretty: Pretty-print JSON

        Returns:
            Number of exported memories
        """
        output_path = Path(output_path)
        logger.info(f"Exporting memories to JSON: {output_path}")

        memories = await self._fetch_memories(scope, user_id, chat_id)
        logger.info(f"Found {len(memories)} memories to export")

        export_data = {
            "export_metadata": {
                "export_time": datetime.now(UTC).isoformat(),
                "total_memories": len(memories),
                "filters": {
                    "scope": scope.value if scope else "all",
                    "user_id": user_id or "all",
                    "chat_id": chat_id or "all",
                },
                "include_embeddings": include_embeddings,
            },
            "memories": [
                self._memory_to_dict(memory, include_embeddings)
                for memory in memories
            ],
        }

        indent = 2 if pretty else None
        output_path.write_text(
            json.dumps(export_data, indent=indent, ensure_ascii=False),
            encoding="utf-8"
        )

        logger.info(f"Exported {len(memories)} memories to {output_path}")
        return len(memories)

    async def export_to_jsonl(
        self,
        output_path: str | Path,
        scope: MemoryScope | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        include_embeddings: bool = False,
    ) -> int:
        """Export memories to JSONL (line-delimited JSON).

        Each line is a separate JSON object.

        Args:
            output_path: Output file path
            scope: Filter by scope (optional)
            user_id: Filter by user (optional)
            chat_id: Filter by chat (optional)
            include_embeddings: Include embedding vectors

        Returns:
            Number of exported memories
        """
        output_path = Path(output_path)
        logger.info(f"Exporting memories to JSONL: {output_path}")

        memories = await self._fetch_memories(scope, user_id, chat_id)
        logger.info(f"Found {len(memories)} memories to export")

        with output_path.open("w", encoding="utf-8") as f:
            for memory in memories:
                memory_dict = self._memory_to_dict(memory, include_embeddings)
                f.write(json.dumps(memory_dict, ensure_ascii=False) + "\n")

        logger.info(f"Exported {len(memories)} memories to {output_path}")
        return len(memories)

    async def export_to_markdown(
        self,
        output_path: str | Path,
        scope: MemoryScope | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        group_by: Literal["scope", "kind", "user", "chat"] = "scope",
    ) -> int:
        """Export memories to Markdown file.

        Args:
            output_path: Output file path
            scope: Filter by scope (optional)
            user_id: Filter by user (optional)
            chat_id: Filter by chat (optional)
            group_by: How to group memories

        Returns:
            Number of exported memories
        """
        output_path = Path(output_path)
        logger.info(f"Exporting memories to Markdown: {output_path}")

        memories = await self._fetch_memories(scope, user_id, chat_id)
        logger.info(f"Found {len(memories)} memories to export")

        # Generate markdown
        md_lines = [
            "# Memory Export",
            "",
            f"**Export Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Total Memories:** {len(memories)}  ",
            f"**Filters:** scope={scope.value if scope else 'all'}, user={user_id or 'all'}, chat={chat_id or 'all'}",
            "",
            "---",
            "",
        ]

        # Group memories
        groups = self._group_memories(memories, group_by)

        for group_name, group_memories in groups.items():
            md_lines.append(f"## {group_name} ({len(group_memories)} memories)")
            md_lines.append("")

            for i, memory in enumerate(group_memories, 1):
                md_lines.extend(self._memory_to_markdown(memory, i))
                md_lines.append("")

        output_path.write_text("\n".join(md_lines), encoding="utf-8")
        logger.info(f"Exported {len(memories)} memories to {output_path}")
        return len(memories)

    async def _fetch_memories(
        self,
        scope: MemoryScope | None,
        user_id: str | None,
        chat_id: str | None,
    ) -> list[MemoryPiece]:
        """Fetch memories from repository.

        Args:
            scope: Filter by scope
            user_id: Filter by user
            chat_id: Filter by chat

        Returns:
            List of memory pieces
        """
        if scope:
            return await self.memory_repo.get_by_scope(
                scope=scope,
                user_id=user_id,
                chat_id=chat_id,
                limit=10000,
            )
        else:
            # Fetch all scopes
            all_memories = []
            for s in MemoryScope:
                memories = await self.memory_repo.get_by_scope(
                    scope=s,
                    user_id=user_id,
                    chat_id=chat_id,
                    limit=10000,
                )
                all_memories.extend(memories)
            return all_memories

    def _memory_to_dict(self, memory: MemoryPiece, include_embeddings: bool) -> dict:
        """Convert memory piece to dictionary.

        Args:
            memory: Memory piece
            include_embeddings: Include embedding vector

        Returns:
            Dictionary representation
        """
        data = {
            "id": memory.id,
            "kind": memory.kind.value,
            "content": memory.content,
            "confidence": memory.confidence,
            "importance": memory.importance,
            "scope": memory.scope.value,
            "user_id": memory.user_id,
            "chat_id": memory.chat_id,
            "channel": memory.channel,
            "source_type": memory.source_type,
            "source_message_ids": memory.source_message_ids,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
            "last_used": memory.last_used.isoformat(),
            "usage_count": memory.usage_count,
            "retrieval_cues": memory.retrieval_cues,
            "entities": memory.entities,
            "metadata": memory.metadata,
        }

        if include_embeddings:
            data["embedding"] = memory.embedding
            data["embedding_dimension"] = len(memory.embedding) if memory.embedding else 0
        else:
            data["has_embedding"] = bool(memory.embedding)
            data["embedding_dimension"] = len(memory.embedding) if memory.embedding else 0

        return data

    def _memory_to_markdown(self, memory: MemoryPiece, index: int) -> list[str]:
        """Convert memory to markdown lines.

        Args:
            memory: Memory piece
            index: Index number

        Returns:
            List of markdown lines
        """
        lines = [
            f"### Memory #{index}: {memory.kind.value}",
            "",
            f"**ID:** `{memory.id}`  ",
            f"**Scope:** {memory.scope.value}  ",
            f"**Confidence:** {memory.confidence:.2f} | **Importance:** {memory.importance:.2f}  ",
            f"**Usage:** {memory.usage_count} times (last: {memory.last_used.strftime('%Y-%m-%d %H:%M')})  ",
        ]

        if memory.user_id:
            lines.append(f"**User:** {memory.user_id}  ")
        if memory.chat_id:
            lines.append(f"**Chat:** {memory.chat_id}  ")
        if memory.channel:
            lines.append(f"**Channel:** {memory.channel}  ")

        lines.extend([
            f"**Created:** {memory.created_at.strftime('%Y-%m-%d %H:%M')}  ",
            f"**Source:** {memory.source_type}  ",
            "",
            "**Content:**",
            "",
            f"> {memory.content.replace(chr(10), chr(10) + '> ')}",
            "",
        ])

        if memory.retrieval_cues:
            lines.append(f"**Retrieval Cues:** {', '.join(memory.retrieval_cues)}  ")
        if memory.entities:
            lines.append(f"**Entities:** {', '.join(memory.entities)}  ")

        lines.append("---")
        return lines

    def _group_memories(
        self,
        memories: list[MemoryPiece],
        group_by: str,
    ) -> dict[str, list[MemoryPiece]]:
        """Group memories by attribute.

        Args:
            memories: List of memories
            group_by: Attribute to group by

        Returns:
            Dictionary of grouped memories
        """
        groups: dict[str, list[MemoryPiece]] = {}

        for memory in memories:
            if group_by == "scope":
                key = memory.scope.value
            elif group_by == "kind":
                key = memory.kind.value
            elif group_by == "user":
                key = memory.user_id or "none"
            elif group_by == "chat":
                key = memory.chat_id or "none"
            else:
                key = "all"

            if key not in groups:
                groups[key] = []
            groups[key].append(memory)

        return groups
