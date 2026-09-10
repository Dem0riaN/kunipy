"""Migration script from C++ kuni diary to kunipy memory system.

This script migrates:
1. Diary entries from C++ kuni format to kunipy MemoryPiece
2. User facts and context
3. Conversation history
4. Embeddings (regenerates if needed)

Usage:
    python -m src.tools.migrate_legacy_diary --kuni-dir /path/to/kuni/diary --output-dir ./data/memory
"""

import argparse
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..domain.memory.models import MemoryPiece
from ..interfaces.llm import IEmbeddingProvider
from ..interfaces.memory import MemoryKind, MemoryScope

logger = logging.getLogger(__name__)


class LegacyDiaryMigrator:
    """Migrate C++ kuni diary to kunipy memory system."""

    def __init__(
        self,
        kuni_diary_dir: Path,
        embedding_provider: IEmbeddingProvider,
    ):
        """Initialize migrator.

        Args:
            kuni_diary_dir: Path to C++ kuni diary directory
            embedding_provider: Embedding provider for regenerating embeddings
        """
        self.kuni_dir = kuni_diary_dir
        self.embedder = embedding_provider
        self.stats = {
            "entries_processed": 0,
            "entries_migrated": 0,
            "errors": 0,
        }

    async def migrate(self) -> list[MemoryPiece]:
        """Run migration.

        Returns:
            List of migrated memory pieces
        """
        logger.info(f"Starting migration from {self.kuni_dir}")

        memories: list[MemoryPiece] = []

        # Migrate diary entries
        diary_entries = self._find_diary_entries()
        for entry_path in diary_entries:
            try:
                memory = await self._migrate_entry(entry_path)
                if memory:
                    memories.append(memory)
                    self.stats["entries_migrated"] += 1
                self.stats["entries_processed"] += 1
            except (ValueError, KeyError, TypeError, OSError) as e:
                logger.error(f"Failed to migrate {entry_path}: {e}")
                self.stats["errors"] += 1

        logger.info(
            f"Migration complete: {self.stats['entries_migrated']}/{self.stats['entries_processed']} "
            f"entries migrated, {self.stats['errors']} errors"
        )

        return memories

    def _find_diary_entries(self) -> list[Path]:
        """Find all diary entry files in C++ kuni directory.

        Returns:
            List of diary entry file paths
        """
        if not self.kuni_dir.exists():
            logger.warning(f"Kuni diary directory not found: {self.kuni_dir}")
            return []

        # C++ kuni stores entries as .txt files with timestamp prefix
        # Format: YYYY-MM-DD_HH-MM-SS_*.txt
        entries = list(self.kuni_dir.glob("*.txt"))
        logger.info(f"Found {len(entries)} diary entries")
        return entries

    async def _migrate_entry(self, entry_path: Path) -> MemoryPiece | None:
        """Migrate single diary entry to MemoryPiece.

        Args:
            entry_path: Path to diary entry file

        Returns:
            MemoryPiece if migration successful, None otherwise
        """
        content = entry_path.read_text(encoding="utf-8")

        # Parse C++ diary entry format
        metadata = self._parse_entry_metadata(entry_path.name, content)
        if not metadata:
            return None

        # Extract text content
        text_content = self._extract_text_content(content)
        if not text_content:
            return None

        # Generate embedding
        embedding = await self.embedder.embedding(text_content)

        # Create MemoryPiece
        memory = MemoryPiece(
            id=str(uuid.uuid4()),
            kind=metadata.get("kind", MemoryKind.EVENT),
            content=text_content,
            confidence=metadata.get("confidence", 1.0),
            importance=metadata.get("importance", 0.5),
            created_at=metadata["created_at"],
            updated_at=metadata.get("updated_at", metadata["created_at"]),
            last_used=metadata["created_at"],
            usage_count=0,
            embedding=embedding,
            scope=metadata.get("scope", MemoryScope.PRIVATE),
            user_id=metadata.get("user_id"),
            chat_id=metadata.get("chat_id"),
            source_type="migration",
            metadata={"legacy_filename": entry_path.name},
        )

        logger.debug(f"Migrated: {entry_path.name} → {memory.id}")
        return memory

    def _parse_entry_metadata(self, filename: str, content: str) -> dict[str, Any] | None:
        """Parse metadata from C++ diary entry.

        Args:
            filename: Entry filename
            content: Entry file content

        Returns:
            Metadata dict or None if parsing failed
        """
        # Extract timestamp from filename (YYYY-MM-DD_HH-MM-SS_*.txt)
        timestamp_match = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})", filename)
        if not timestamp_match:
            logger.warning(f"Could not parse timestamp from filename: {filename}")
            return None

        date_str = timestamp_match.group(1)
        time_str = timestamp_match.group(2).replace("-", ":")
        created_at = datetime.fromisoformat(f"{date_str} {time_str}")
        created_at = created_at.replace(tzinfo=UTC)

        # Parse metadata from content (C++ format: key: value)
        metadata: dict[str, Any] = {"created_at": created_at}

        # Look for metadata markers in content
        if "confidence:" in content:
            match = re.search(r"confidence:\s*([-\d.]+)", content)
            if match:
                metadata["confidence"] = float(match.group(1))

        if "importance:" in content:
            match = re.search(r"importance:\s*([\d.]+)", content)
            if match:
                metadata["importance"] = float(match.group(1))

        if "user_id:" in content:
            match = re.search(r"user_id:\s*(\d+)", content)
            if match:
                metadata["user_id"] = match.group(1)

        if "chat_id:" in content:
            match = re.search(r"chat_id:\s*([-\d]+)", content)
            if match:
                metadata["chat_id"] = match.group(1)

        # Determine kind based on content
        if "fact:" in content.lower():
            metadata["kind"] = MemoryKind.FACT
        elif "thought:" in content.lower():
            metadata["kind"] = MemoryKind.THOUGHT
        elif "entity:" in content.lower():
            metadata["kind"] = MemoryKind.ENTITY_DESCRIPTION
        else:
            metadata["kind"] = MemoryKind.EVENT

        return metadata

    def _extract_text_content(self, content: str) -> str:
        """Extract clean text content from C++ diary entry.

        Args:
            content: Raw entry content

        Returns:
            Cleaned text content
        """
        # Remove metadata lines
        lines = content.split("\n")
        text_lines = []

        for line in lines:
            # Skip metadata lines (key: value format)
            if re.match(r"^\w+:", line):
                continue
            # Skip empty lines
            if not line.strip():
                continue
            text_lines.append(line)

        return "\n".join(text_lines).strip()


async def migrate_legacy_diary(
    kuni_dir: Path,
    embedding_provider: IEmbeddingProvider,
    output_path: Path | None = None,
) -> list[MemoryPiece]:
    """Migrate C++ kuni diary to kunipy format.

    Args:
        kuni_dir: Path to C++ kuni diary directory
        embedding_provider: Embedding provider
        output_path: Optional path to save migrated memories as JSON

    Returns:
        List of migrated memory pieces
    """
    migrator = LegacyDiaryMigrator(kuni_dir, embedding_provider)
    memories = await migrator.migrate()

    if output_path and memories:
        # Save as JSON for inspection
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "id": m.id,
                        "kind": m.kind.value,
                        "content": m.content,
                        "confidence": m.confidence,
                        "importance": m.importance,
                        "created_at": m.created_at.isoformat(),
                        "scope": m.scope.value,
                        "user_id": m.user_id,
                        "chat_id": m.chat_id,
                        "metadata": m.metadata,
                    }
                    for m in memories
                ],
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"Saved migration report to {output_path}")

    return memories


def main():
    """CLI entry point for migration script."""
    parser = argparse.ArgumentParser(description="Migrate C++ kuni diary to kunipy")
    parser.add_argument(
        "--kuni-dir",
        type=Path,
        required=True,
        help="Path to C++ kuni diary directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./data/migration_report.json"),
        help="Output path for migration report",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print(f"Migrating from {args.kuni_dir} to {args.output}")
    print("Note: This is a dry-run. Implement embedding provider integration to run migration.")


if __name__ == "__main__":
    main()
