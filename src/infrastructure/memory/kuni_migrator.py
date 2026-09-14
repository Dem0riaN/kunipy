"""Migration tool: C++ kuni → kunipy (ТЗ-002 пункт 22, Этап 5).

Migrates diary entries from original C++ kuni format to new kunipy memory system.
Preserves embeddings, confidence, usage statistics, and creates proper provenance.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from ...config import Config
from ...interfaces.llm import IEmbeddingProvider
from ...interfaces.memory import MemoryKind, MemoryPiece, MemoryScope
from .kuni_archive_reader import KuniArchiveReader, KuniEntry
from .memory_service import MemoryService

logger = logging.getLogger(__name__)


class KuniMigrator:
    """Migrates C++ kuni diary to kunipy memory system.

    Handles:
    - Reading old archive format
    - Determining memory scope
    - Preserving or regenerating embeddings
    - Setting confidence
    - Creating provenance tracking
    - Progress reporting

    Writes go through MemoryService (dual-write to ChromaDB + SQLite).
    """

    def __init__(
        self,
        archive_reader: KuniArchiveReader,
        memory_service: MemoryService,
        embedding_provider: IEmbeddingProvider,
        config: Config,
    ):
        """Initialize migrator.

        Args:
            archive_reader: Reader for C++ kuni archive
            memory_service: High-level memory service (ChromaDB + SQLite dual-write)
            embedding_provider: Embedding provider for regenerating vectors
            config: Application configuration
        """
        self.archive_reader = archive_reader
        self.memory_service = memory_service
        self.embedding_provider = embedding_provider
        self.config = config

    async def migrate(
        self,
        target_user_id: str | None = None,
        target_chat_id: str | None = None,
        default_scope: MemoryScope = MemoryScope.GLOBAL,
        regenerate_embeddings: bool = False,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Migrate all entries from kuni archive.

        Args:
            target_user_id: Target user ID (if migrating to specific user)
            target_chat_id: Target chat ID (if migrating to specific chat)
            default_scope: Default memory scope for entries
            regenerate_embeddings: Force regeneration of embeddings
            dry_run: If True, don't write to database

        Returns:
            Migration result with statistics
        """
        logger.info("Starting kuni → kunipy migration")
        logger.info(f"Archive: {self.archive_reader.diary_dir}")
        logger.info(f"Target user: {target_user_id or 'NONE'}")
        logger.info(f"Target chat: {target_chat_id or 'NONE'}")
        logger.info(f"Default scope: {default_scope.value}")
        logger.info(f"Regenerate embeddings: {regenerate_embeddings}")
        logger.info(f"Dry run: {dry_run}")

        # Get archive statistics
        stats = self.archive_reader.get_statistics()
        logger.info(f"Archive contains {stats['total_entries']} entries")
        logger.info(f"Entries with embeddings: {stats['entries_with_embedding']}")
        logger.info(f"Entries without embeddings: {stats['entries_without_embedding']}")

        # Ensure target user/chat exist
        if target_user_id and not dry_run:
            await self.memory_service.user_repo.get_or_create_user(
                user_id=target_user_id,
                display_name=f"Migrated User {target_user_id}"
            )

        if target_chat_id and not dry_run:
            await self.memory_service.chat_repo.get_or_create_chat(
                chat_id=target_chat_id,
                chat_type="private",
                title="Migrated Chat"
            )

        result = MigrationResult()

        # Migrate entries
        for i, entry in enumerate(self.archive_reader.read_all(), 1):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{stats['total_entries']}")

            try:
                memory_piece = await self._convert_entry(
                    entry=entry,
                    target_user_id=target_user_id,
                    target_chat_id=target_chat_id,
                    default_scope=default_scope,
                    regenerate_embeddings=regenerate_embeddings,
                )

                if not dry_run:
                    # Dual-write: ChromaDB (vectors) + SQLite (metadata)
                    await self.memory_service.create_memory(memory_piece)

                result.migrated_count += 1
                result.migrated_ids.append(entry.id)

            except Exception as e:
                logger.error(f"Failed to migrate entry {entry.id}: {e}")
                result.failed_count += 1
                result.failed_ids.append(entry.id)
                result.errors.append(str(e))

        logger.info("Migration complete!")
        logger.info(f"Migrated: {result.migrated_count}")
        logger.info(f"Failed: {result.failed_count}")

        if result.regenerated_embeddings_count > 0:
            logger.info(f"Regenerated embeddings: {result.regenerated_embeddings_count}")

        return result

    async def _convert_entry(
        self,
        entry: KuniEntry,
        target_user_id: str | None,
        target_chat_id: str | None,
        default_scope: MemoryScope,
        regenerate_embeddings: bool,
    ) -> MemoryPiece:
        """Convert single kuni entry to memory piece.

        Args:
            entry: Kuni archive entry
            target_user_id: Target user ID
            target_chat_id: Target chat ID
            default_scope: Default scope
            regenerate_embeddings: Force regeneration

        Returns:
            Converted MemoryPiece
        """
        # Determine memory kind from content
        kind = self._determine_memory_kind(entry)

        # Determine scope
        scope = self._determine_scope(entry, default_scope, target_user_id, target_chat_id)

        # Get embedding
        if entry.embedding and not regenerate_embeddings:
            # Use existing embedding
            embedding = entry.embedding
        else:
            # Regenerate embedding
            logger.debug(f"Generating embedding for {entry.id}")
            embedding_result = await self.embedding_provider.embedding(entry.freeform_body)
            embedding = embedding_result.tolist() if hasattr(embedding_result, 'tolist') else list(embedding_result)

        # Parse timestamp from ID (if it's unix timestamp)
        created_at = self._parse_timestamp(entry.id)

        # Create memory piece
        memory_piece = MemoryPiece(
            id=str(uuid.uuid4()),  # New UUID
            kind=kind,
            content=entry.freeform_body,
            confidence=entry.confidence,
            importance=self._calculate_importance(entry),
            scope=scope,
            user_id=target_user_id,
            chat_id=target_chat_id,
            channel=None,  # Unknown from archive
            embedding=embedding,
            source_type="migration",
            source_message_ids=[],  # No message IDs in old format
            created_at=created_at,
            updated_at=datetime.now(UTC),
            last_used=self._parse_last_used(entry.last_used),
            usage_count=entry.usage_count,
            retrieval_cues=[],
            entities=[],
            metadata={
                "migrated_from_kuni": True,
                "original_id": entry.id,
                "original_score": entry.score,
                "migration_date": datetime.now(UTC).isoformat(),
            }
        )

        return memory_piece

    def _determine_memory_kind(self, entry: KuniEntry) -> MemoryKind:
        """Determine memory kind from entry content.

        Uses heuristics based on content analysis.

        Args:
            entry: Kuni entry

        Returns:
            MemoryKind enum value
        """
        content_lower = entry.freeform_body.lower()

        # Heuristics
        if any(word in content_lower for word in ["чувствует", "думает", "размышляет", "рефлекс", "feels", "thinks"]):
            return MemoryKind.THOUGHT

        if any(word in content_lower for word in ["произошло", "случилось", "happened", "occurred", "событие"]):
            return MemoryKind.EVENT

        if any(word in content_lower for word in ["это", "является", "представляет", "is", "represents"]):
            return MemoryKind.ENTITY_DESCRIPTION

        # Default to FACT
        return MemoryKind.FACT

    def _determine_scope(
        self,
        entry: KuniEntry,
        default_scope: MemoryScope,
        target_user_id: str | None,
        target_chat_id: str | None,
    ) -> MemoryScope:
        """Determine memory scope.

        Args:
            entry: Kuni entry
            default_scope: Default scope
            target_user_id: Target user ID
            target_chat_id: Target chat ID

        Returns:
            MemoryScope enum value
        """
        # If migrating to specific user/chat, use appropriate scope
        if target_user_id and target_chat_id:
            return MemoryScope.CHAT
        elif target_user_id:
            return MemoryScope.USER
        else:
            return default_scope

    def _calculate_importance(self, entry: KuniEntry) -> float:
        """Calculate importance from usage statistics.

        Args:
            entry: Kuni entry

        Returns:
            Importance value (0.0 to 1.0)
        """
        # Base importance on usage count and confidence
        usage_factor = min(entry.usage_count / 10.0, 1.0)  # Cap at 10 uses
        confidence_factor = (entry.confidence + 1.0) / 2.0  # Map -1..1 to 0..1

        # Weighted average
        importance = (usage_factor * 0.6 + confidence_factor * 0.4)
        return max(0.0, min(1.0, importance))

    def _parse_timestamp(self, entry_id: str) -> datetime:
        """Parse timestamp from entry ID.

        Args:
            entry_id: Entry ID (usually unix timestamp)

        Returns:
            Datetime object
        """
        try:
            timestamp = int(entry_id)
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (ValueError, OSError):
            # Not a timestamp, use current time
            return datetime.now(UTC)

    def _parse_last_used(self, last_used: str) -> datetime:
        """Parse last_used timestamp.

        Args:
            last_used: Last used string

        Returns:
            Datetime object
        """
        if last_used == "never":
            return datetime.now(UTC)

        try:
            # Try parsing as ISO format
            return datetime.fromisoformat(last_used.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.now(UTC)


class MigrationResult:
    """Result of migration operation."""

    def __init__(self):
        self.migrated_count: int = 0
        self.failed_count: int = 0
        self.regenerated_embeddings_count: int = 0
        self.migrated_ids: list[str] = []
        self.failed_ids: list[str] = []
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "migrated_count": self.migrated_count,
            "failed_count": self.failed_count,
            "regenerated_embeddings_count": self.regenerated_embeddings_count,
            "total_processed": self.migrated_count + self.failed_count,
            "success_rate": self.migrated_count / (self.migrated_count + self.failed_count) if (self.migrated_count + self.failed_count) > 0 else 0.0,
        }
