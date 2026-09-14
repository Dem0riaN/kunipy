"""Archive reader for original C++ kuni diary format (ТЗ-002 пункт 23).

Reads the legacy markdown-based diary format from the original kuni project.
Format: directory with .md files, each containing JSON metadata block and freeform text.

Example file structure:
    diary/
    ├── 1234567890.md
    ├── 1234567891.md
    └── 1234567892.md

Each .md file format:
    ---
    {"score": 0.0, "confidence": 0.5, "lastUsed": "2024-01-01", "usageCount": 5, "embedding": [0.1, 0.2, ...]}
    ---
    This is the actual diary entry content.
    Multiple lines are supported.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class KuniEntry:
    """Single entry from C++ kuni diary archive.

    Represents a parsed diary entry with metadata and content.
    """
    # Identity
    id: str  # Filename without .md extension (usually timestamp)

    # Content
    freeform_body: str  # Main text content

    # Metadata (from JSON block)
    score: float = 0.0
    confidence: float = 0.0
    last_used: str = "never"
    usage_count: int = 0
    embedding: list[float] | None = None

    # File info
    file_path: Path | None = None
    file_size: int = 0


class KuniArchiveReader:
    """Reader for original C++ kuni diary format.

    Provides read-only access to legacy diary archives without modification.
    """

    def __init__(self, diary_dir: str | Path):
        """Initialize reader.

        Args:
            diary_dir: Path to directory containing .md diary files
        """
        self.diary_dir = Path(diary_dir)

        if not self.diary_dir.exists():
            raise FileNotFoundError(f"Diary directory not found: {self.diary_dir}")

        if not self.diary_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.diary_dir}")

        logger.info(f"Initialized KuniArchiveReader for: {self.diary_dir}")

    def list_entries(self) -> list[str]:
        """List all entry IDs in the archive.

        Returns:
            List of entry IDs (filenames without .md extension)
        """
        entries = []
        for file_path in self.diary_dir.glob("*.md"):
            entry_id = file_path.stem
            entries.append(entry_id)

        entries.sort()  # Sort by ID (usually timestamp)
        logger.debug(f"Found {len(entries)} diary entries")
        return entries

    def read_entry(self, entry_id: str) -> KuniEntry | None:
        """Read single diary entry.

        Args:
            entry_id: Entry ID (filename without .md)

        Returns:
            Parsed KuniEntry or None if not found
        """
        file_path = self.diary_dir / f"{entry_id}.md"

        if not file_path.exists():
            logger.warning(f"Entry not found: {entry_id}")
            return None

        try:
            return self._parse_file(file_path, entry_id)
        except Exception as e:
            logger.error(f"Failed to parse entry {entry_id}: {e}")
            return None

    def read_all(self) -> Iterator[KuniEntry]:
        """Read all diary entries.

        Yields:
            Parsed KuniEntry objects
        """
        entry_ids = self.list_entries()
        logger.info(f"Reading {len(entry_ids)} diary entries...")

        for i, entry_id in enumerate(entry_ids, 1):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(entry_ids)}")

            entry = self.read_entry(entry_id)
            if entry:
                yield entry

    def _parse_file(self, file_path: Path, entry_id: str) -> KuniEntry:
        """Parse single .md file.

        Args:
            file_path: Path to .md file
            entry_id: Entry ID

        Returns:
            Parsed KuniEntry

        Raises:
            ValueError: If file format is invalid
        """
        content = file_path.read_text(encoding="utf-8")
        file_size = file_path.stat().st_size

        # Check for metadata block
        if not content.startswith("---"):
            # No metadata, just body
            logger.debug(f"Entry {entry_id} has no metadata block")
            return KuniEntry(
                id=entry_id,
                freeform_body=content.strip(),
                file_path=file_path,
                file_size=file_size,
            )

        # Find end of metadata block
        end_marker = content.find("---", 4)
        if end_marker == -1:
            raise ValueError(f"Malformed metadata block in {entry_id}: no closing ---")

        # Extract metadata JSON
        metadata_json = content[4:end_marker].strip()
        freeform_body = content[end_marker + 3:].strip()

        # Parse metadata
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in metadata block: {e}")

        # Extract embedding
        embedding = metadata.get("embedding")
        if embedding is not None and not isinstance(embedding, list):
            # Sometimes embedding might be stored differently
            logger.warning(f"Entry {entry_id}: embedding is not a list, skipping")
            embedding = None

        return KuniEntry(
            id=entry_id,
            freeform_body=freeform_body,
            score=float(metadata.get("score", 0.0)),
            confidence=float(metadata.get("confidence", 0.0)),
            last_used=metadata.get("lastUsed", "never"),
            usage_count=int(metadata.get("usageCount", 0)),
            embedding=embedding,
            file_path=file_path,
            file_size=file_size,
        )

    def get_statistics(self) -> dict:
        """Get archive statistics.

        Returns:
            Dictionary with statistics about the archive
        """
        entry_ids = self.list_entries()
        total_entries = len(entry_ids)

        entries_with_embedding = 0
        entries_without_embedding = 0
        total_size = 0
        confidence_distribution = {"negative": 0, "zero": 0, "positive": 0}

        for entry in self.read_all():
            total_size += entry.file_size

            if entry.embedding:
                entries_with_embedding += 1
            else:
                entries_without_embedding += 1

            if entry.confidence < -0.01:
                confidence_distribution["negative"] += 1
            elif entry.confidence > 0.01:
                confidence_distribution["positive"] += 1
            else:
                confidence_distribution["zero"] += 1

        return {
            "total_entries": total_entries,
            "entries_with_embedding": entries_with_embedding,
            "entries_without_embedding": entries_without_embedding,
            "total_size_bytes": total_size,
            "confidence_distribution": confidence_distribution,
            "diary_dir": str(self.diary_dir),
        }

    def export_to_json(self, output_path: str | Path) -> None:
        """Export archive to JSON format.

        Args:
            output_path: Path to output JSON file
        """
        output_path = Path(output_path)

        entries_data = []
        for entry in self.read_all():
            entries_data.append({
                "id": entry.id,
                "freeform_body": entry.freeform_body,
                "score": entry.score,
                "confidence": entry.confidence,
                "last_used": entry.last_used,
                "usage_count": entry.usage_count,
                "has_embedding": entry.embedding is not None,
                "embedding_dimension": len(entry.embedding) if entry.embedding else 0,
            })

        output_path.write_text(json.dumps(entries_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Exported {len(entries_data)} entries to {output_path}")
