"""File I/O for diary .md entries (Phase 1).

Reads both C++ kuni format and legacy kunipy format; writes C++ format only.
Separate from Diary (SRP, замечание 6-7) — Diary delegates all file ops here.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...diary import DiaryEntry

logger = logging.getLogger(__name__)


class DiaryFileStore:
    """File I/O for diary .md entries.

    Reads BOTH formats, writes C++ format only:
        C++ format:   ---\\n{single-line JSON}\\n---\\n\\n{body}
        Legacy kunipy: ```json\\n{json metadata}\\n```\\n\\n{body}
    """

    def __init__(self, diary_dir: Path | str):
        """Initialize file store.

        Args:
            diary_dir: Directory containing diary .md files
        """
        self._diary_dir = Path(diary_dir)
        self._diary_dir.mkdir(parents=True, exist_ok=True)

    @property
    def diary_dir(self) -> Path:
        return self._diary_dir

    def save(self, entry: DiaryEntry) -> None:
        """Write entry in C++ format.

        Format:
            ---
            {single-line JSON metadata}
            ---

            {body text}

        File ID = bare Unix timestamp (created_at) when available,
        otherwise the entry.id.
        """
        # Determine filename: use created_at if available, else entry.id
        created_at = entry.metadata.get("created_at")
        if created_at and isinstance(created_at, int):
            file_id = str(created_at)
        else:
            file_id = entry.id

        file_path = self._diary_dir / f"{file_id}.md"

        # Build metadata JSON (exclude embedding from file — too large for .md)
        meta = {k: v for k, v in entry.metadata.items() if k != "embedding"}
        meta_line = json.dumps(meta, ensure_ascii=False)

        content = f"---\n{meta_line}\n---\n\n{entry.body}"
        file_path.write_text(content, encoding="utf-8")

    def load(self, entry_id: str) -> DiaryEntry | None:
        """Load a single entry by ID.

        Args:
            entry_id: File stem (without .md)

        Returns:
            DiaryEntry or None if not found
        """

        file_path = self._diary_dir / f"{entry_id}.md"
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            return self.parse_file_content(entry_id, content)
        except (OSError, ValueError, KeyError) as e:
            logger.error(f"Failed to load diary entry {entry_id}: {e}")
            return None

    def load_all(self) -> list[DiaryEntry]:
        """Load all .md entries from diary_dir.

        Returns:
            List of DiaryEntry objects
        """

        entries = []
        for file_path in self._diary_dir.glob("*.md"):
            file_id = file_path.stem
            try:
                content = file_path.read_text(encoding="utf-8")
                entry = self.parse_file_content(file_id, content)
                entries.append(entry)
            except (ValueError, KeyError, TypeError, OSError) as e:
                logger.error(f"Failed to load diary entry {file_id}: {e}")

        return entries

    def delete(self, entry_id: str) -> None:
        """Remove .md file for an entry.

        Used after migration to ChromaDB (замечание 2: file deleted after migration).

        Args:
            entry_id: File stem (without .md)
        """
        file_path = self._diary_dir / f"{entry_id}.md"
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted diary file: {file_path}")

    def list_entries(
        self,
        sort_by: str = "date",
        limit: int | None = None,
    ) -> list[DiaryEntry]:
        """List entries sorted and optionally limited.

        Args:
            sort_by: Sort field ('date', 'confidence', 'importance', 'score')
            limit: Maximum entries to return

        Returns:
            List of DiaryEntry objects
        """
        entries = self.load_all()

        if sort_by == "date":
            entries.sort(
                key=lambda e: e.metadata.get("created_at", 0),
                reverse=True,
            )
        elif sort_by == "confidence":
            entries.sort(
                key=lambda e: e.metadata.get("confidence", 0.0),
                reverse=True,
            )
        elif sort_by == "importance":
            entries.sort(
                key=lambda e: e.metadata.get("importance", 0.5),
                reverse=True,
            )
        elif sort_by == "score":
            entries.sort(
                key=lambda e: e.metadata.get("score", 0.0),
                reverse=True,
            )

        if limit is not None:
            entries = entries[:limit]

        return entries

    @staticmethod
    def parse_file_content(file_id: str, content: str) -> DiaryEntry:
        """Parse diary entry from file content.

        Handles both formats:

        **C++ format (real, 115 files in G:\\AI\\diary):**
            ---
            {"score": 0.0, "confidence": 0.5, "lastUsed": "never",
             "usageCount": 0, "embedding": [...]}
            ---

            {body}

        **Legacy kunipy (incorrect, fixed by migration):**
            ```json
            {json metadata}
            ```

            {body}

        **ID handling (замечание 3):**
        - file_id = bare Unix timestamp ("1789107034") → created_at = int(file_id)
        - file_id with prefix ("entry_20260912153045_1234") →
          created_at = int(time.time()) (fallback, filename not a timestamp)
        - Body timestamp is LLM-authored → NOT used as source of truth
        """
        from ...diary import DiaryEntry

        metadata: dict[str, Any] = {}
        body = content

        # Try C++ format: ---\\n{JSON}\\n---\\n\\n{body}
        if content.startswith("---"):
            end_idx = content.find("\n---", 4)
            if end_idx > 0:
                json_str = content[3:end_idx].strip()
                try:
                    metadata = json.loads(json_str)
                    body = content[end_idx + 4:].strip()
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse C++ format metadata for {file_id}")

        # Try legacy kunipy format: ```json\\n{json}\\n```\\n\\n{body}
        elif content.startswith("```json"):
            end_idx = content.find("```", 7)
            if end_idx > 0:
                try:
                    metadata = json.loads(content[7:end_idx])
                    body = content[end_idx + 3:].strip()
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse legacy format metadata for {file_id}")

        # Derive created_at from filename (замечание 3)
        created_at = DiaryFileStore._derive_created_at(file_id)
        if "created_at" not in metadata:
            metadata["created_at"] = created_at
        else:
            # Keep original created_at but store source_timestamp for audit
            metadata.setdefault("source_timestamp", file_id)

        # Migrate snake_case to camelCase for consistency
        metadata = DiaryFileStore._normalize_metadata_keys(metadata)

        return DiaryEntry(
            id=file_id,
            text=content,
            metadata=metadata,
            body=body,
        )

    @staticmethod
    def _derive_created_at(file_id: str) -> int:
        """Derive created_at Unix timestamp from file_id.

        Args:
            file_id: File stem (e.g., "1789107034" or "entry_20260912153045_1234")

        Returns:
            Unix timestamp as int
        """
        # Try bare Unix timestamp
        try:
            ts = int(file_id)
            # Sanity check: should be a reasonable Unix timestamp
            if 1_000_000_000 <= ts <= 3_000_000_000:
                return ts
        except (ValueError, TypeError):
            pass

        # Fallback: current time
        return int(time.time())

    @staticmethod
    def _normalize_metadata_keys(metadata: dict[str, Any]) -> dict[str, Any]:
        """Normalize metadata keys to camelCase (C++ format).

        Legacy kunipy uses snake_case (last_used, usage_count).
        C++ format uses camelCase (lastUsed, usageCount).

        Args:
            metadata: Raw metadata dict

        Returns:
            Normalized metadata dict
        """
        key_map = {
            "last_used": "lastUsed",
            "usage_count": "usageCount",
            "source_channel": "sourceChannel",
        }
        for old_key, new_key in key_map.items():
            if old_key in metadata and new_key not in metadata:
                metadata[new_key] = metadata.pop(old_key)

        # Ensure expected fields have defaults
        metadata.setdefault("score", 0.0)
        metadata.setdefault("confidence", 0.0)
        metadata.setdefault("lastUsed", "never")
        metadata.setdefault("usageCount", 0)
        metadata.setdefault("importance", 0.5)
        metadata.setdefault("kind", "other")
        metadata.setdefault("tags", "")
        metadata.setdefault("visibility", "chat")
        metadata.setdefault("user_id", "")
        metadata.setdefault("chat_id", "")
        metadata.setdefault("sourceChannel", "")

        return metadata
