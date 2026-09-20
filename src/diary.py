"""Diary memory system with dependency injection.

Phase 1: Delegates to DiaryFileStore and DiaryVectorStore when available,
falls back to legacy file-only behavior for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .config import Config
from .openai_chat import OpenAIChat

if TYPE_CHECKING:
    from .infrastructure.memory.diary_file_store import DiaryFileStore
    from .infrastructure.memory.diary_vector_store import DiaryVectorStore

logger = logging.getLogger(__name__)


@dataclass
class DiaryEntry:
    """A single diary entry with metadata."""
    id: str
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def embedding(self) -> np.ndarray | None:
        """Get embedding vector from metadata."""
        emb = self.metadata.get("embedding")
        if emb is not None:
            return np.array(emb, dtype=np.float64)
        return None

    @embedding.setter
    def embedding(self, value: np.ndarray) -> None:
        self.metadata["embedding"] = value.tolist()

    @property
    def confidence(self) -> float:
        return self.metadata.get("confidence", 0.0)

    @staticmethod
    def from_file_content(file_id: str, content: str) -> DiaryEntry:
        """Parse diary entry from file content.

        Delegates to DiaryFileStore.parse_file_content() which handles both
        the real C++ format (--- JSON front matter) and legacy kunipy format,
        plus normalizes metadata keys and derives created_at (замечание 3).
        """
        from .infrastructure.memory.diary_file_store import DiaryFileStore
        return DiaryFileStore.parse_file_content(file_id, content)


class Diary:
    """Diary memory system with explicit config dependency.

    Phase 1: Accepts optional DiaryFileStore and DiaryVectorStore.
    When both are provided, all I/O goes through them (ChromaDB + C++ format files).
    Without them, falls back to legacy file-only behavior.
    """

    def __init__(
        self,
        diary_dir: str | Path,
        openai_chat: OpenAIChat,
        config: Config,
        embedding_model: str | None = None,
        file_store: DiaryFileStore | None = None,
        vector_store: DiaryVectorStore | None = None,
    ):
        """Initialize diary with dependencies.

        Args:
            diary_dir: Directory for diary entries
            openai_chat: OpenAI client for embeddings
            config: Application configuration
            embedding_model: Override embedding model (optional)
            file_store: File I/O handler (Phase 1, optional)
            vector_store: ChromaDB store (Phase 1, optional)
        """
        self.diary_dir = Path(diary_dir)
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.openai = openai_chat
        self.config = config
        self.embedding_model = embedding_model or config.embedding.model
        self._cache: dict[str, DiaryEntry] | None = None
        self._lock = asyncio.Lock()
        self._last_entry_id: str | None = None  # Prevent duplicate IDs
        self._entry_counter: int = 0  # Monotonic counter for same-second entries

        # Phase 1: stores (optional — backward compatible)
        self._file_store = file_store
        self._vector_store = vector_store

        # Phase 2: consolidation service (set via setter)
        self._consolidation_service: Any = None

    async def _load_cache(self) -> dict[str, DiaryEntry]:
        """Lazy load all diary entries into memory."""
        if self._cache is not None:
            return self._cache

        async with self._lock:
            if self._cache is not None:
                return self._cache

            if self._file_store:
                # Phase 1: delegate to DiaryFileStore
                entries = self._file_store.load_all()
                cache = {e.id: e for e in entries}
            else:
                # Legacy fallback: read .md files directly
                cache = {}
                for file_path in self.diary_dir.glob("*.md"):
                    file_id = file_path.stem
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        entry = DiaryEntry.from_file_content(file_id, content)
                        cache[file_id] = entry
                    except (ValueError, KeyError, TypeError, OSError) as e:
                        logger.error(f"Failed to load diary entry {file_id}: {e}")

            self._cache = cache
            logger.info(f"Loaded {len(cache)} diary entries")
            return cache

    async def query(
        self,
        query_vector: np.ndarray,
        max_entries: int = 5,
        confidence_factor: float = 0.01,
        min_relatedness: float | None = None,
        filter_fn: Callable[[DiaryEntry], bool] | None = None,
    ) -> list[tuple[DiaryEntry, float]]:
        """Query diary entries by embedding similarity.

        Phase 1: Uses ChromaDB when available, falls back to numpy scan.
        Updates usage stats (score, lastUsed, usageCount) in-place.
        """
        if min_relatedness is None:
            min_relatedness = self.config.diary_min_relatedness

        if self._vector_store:
            return await self._query_chromadb(
                query_vector, max_entries, confidence_factor,
                min_relatedness, filter_fn,
            )

        # Legacy fallback: in-memory numpy scan
        return await self._query_numpy(
            query_vector, max_entries, confidence_factor,
            min_relatedness, filter_fn,
        )

    async def _query_chromadb(
        self,
        query_vector: np.ndarray,
        max_entries: int,
        confidence_factor: float,
        min_relatedness: float,
        filter_fn: Callable[[DiaryEntry], bool] | None,
    ) -> list[tuple[DiaryEntry, float]]:
        """Query via ChromaDB vector store."""
        assert self._vector_store is not None

        # Fetch more results than needed to allow for filtering
        raw = await self._vector_store.query(
            query_embedding=query_vector.tolist(),
            n_results=max_entries * 3,  # oversampling for filter_fn
        )

        results: list[tuple[DiaryEntry, float]] = []
        for hit in raw:
            entry_id = hit["id"]
            metadata = hit.get("metadata", {})
            body = hit.get("document", "")
            embedding = hit.get("embedding")
            distance = hit.get("distance", 0.0)

            # Reconstruct DiaryEntry
            if embedding is not None:
                metadata["embedding"] = embedding

            entry = DiaryEntry(
                id=entry_id,
                body=body,
                metadata=metadata,
            )

            # Apply optional filter
            if filter_fn and not filter_fn(entry):
                continue

            # Convert ChromaDB cosine distance to similarity score
            # ChromaDB cosine space: distance = 1 - cosine_similarity
            similarity = 1.0 - distance
            normalized = (similarity + 1.0) / 2.0
            conf = float(metadata.get("confidence", 0.0))
            final_score = normalized + conf * confidence_factor
            final_score = max(0.0, min(1.0, final_score))

            if final_score >= min_relatedness:
                results.append((entry, final_score))

                # Update usage stats in-place (замечание: original behavior)
                self._update_usage_stats(entry, final_score)
                await self._persist_usage_stats(entry)

            if len(results) >= max_entries:
                break

        results.sort(key=lambda x: x[1], reverse=True)

        # Update cache
        if self._cache is not None:
            for entry, _ in results:
                self._cache[entry.id] = entry

        return results[:max_entries]

    async def _query_numpy(
        self,
        query_vector: np.ndarray,
        max_entries: int,
        confidence_factor: float,
        min_relatedness: float,
        filter_fn: Callable[[DiaryEntry], bool] | None,
    ) -> list[tuple[DiaryEntry, float]]:
        """Legacy fallback: numpy cosine similarity scan."""
        cache = await self._load_cache()
        results: list[tuple[DiaryEntry, float]] = []

        for entry in cache.values():
            if filter_fn and not filter_fn(entry):
                continue

            # Get or compute embedding
            embedding = entry.embedding
            if embedding is None:
                embedding = await self._get_embedding(entry.body)
                entry.embedding = embedding
                await self.save(entry)

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_vector, embedding)
            normalized = (similarity + 1.0) / 2.0
            final_score = normalized + entry.confidence * confidence_factor
            final_score = max(0.0, min(1.0, final_score))

            if final_score >= min_relatedness:
                results.append((entry, final_score))

                # Update usage stats
                self._update_usage_stats(entry, final_score)
                await self._persist_usage_stats(entry)

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_entries]

    def _update_usage_stats(self, entry: DiaryEntry, score: float) -> None:
        """Update usage stats in-place (matches original C++ behavior).

        Mutates: score, usageCount, lastUsed.
        """
        entry.metadata["score"] = score
        entry.metadata["usageCount"] = entry.metadata.get("usageCount", 0) + 1
        entry.metadata["lastUsed"] = datetime.now(self.config.timezone_info).isoformat()

    async def _persist_usage_stats(self, entry: DiaryEntry) -> None:
        """Persist updated usage stats to stores."""
        if self._vector_store:
            embedding = entry.embedding
            if embedding is not None:
                await self._vector_store.add(
                    entry_id=entry.id,
                    embedding=embedding.tolist(),
                    body=entry.body,
                    metadata={k: v for k, v in entry.metadata.items() if k != "embedding"},
                )
        elif self._file_store:
            self._file_store.save(entry)

    async def add_entry(
        self,
        text: str,
        confidence: float = 0.0,
        *,
        visibility: str = "chat",
        user_id: str = "",
        chat_id: str = "",
        source_channel: str = "",
        kind: str = "other",
        importance: float = 0.5,
        tags: str = "",
    ) -> str:
        """Add a new diary entry with optional embedding.

        Phase 1: ID = str(int(time.time())) — Unix timestamp, NOT LLM time (замечание 3).
        Plagiarism check via ChromaDB when available.
        """
        threshold = self.config.diary_plagiarism_threshold

        # Generate embedding
        embedding = await self._get_embedding(text)

        # Plagiarism check
        if confidence < 0.5:
            existing = await self.query(embedding, max_entries=1, min_relatedness=threshold)
            if existing:
                logger.info(f"Skipping duplicate diary entry (similarity {existing[0][1]:.3f})")
                return existing[0][0].id

        # Create new entry with Unix timestamp ID (замечание 3)
        # Ensure uniqueness: when called rapidly (e.g. shutdown dump writes
        # multiple entries in the same second), append a monotonic counter
        # to avoid ID collisions that would silently overwrite via upsert.
        now_ts = int(time.time())
        base_id = str(now_ts)
        if base_id == self._last_entry_id:
            self._entry_counter += 1
            entry_id = f"{base_id}_{self._entry_counter}"
        else:
            self._last_entry_id = base_id
            self._entry_counter = 0
            entry_id = base_id
        entry = DiaryEntry(
            id=entry_id,
            body=text,
            metadata={
                "score": 0.0,
                "confidence": confidence,
                "lastUsed": "never",
                "usageCount": 0,
                "importance": importance,
                "kind": kind,
                "tags": tags,
                "visibility": visibility,
                "user_id": user_id,
                "chat_id": chat_id,
                "sourceChannel": source_channel,
                "created_at": now_ts,
            },
        )
        entry.embedding = embedding

        await self.save(entry)
        logger.info(f"Added diary entry {entry_id}")
        return entry_id

    async def save(self, entry: DiaryEntry) -> None:
        """Save diary entry to disk and/or ChromaDB.

        Phase 1: Delegates to stores when available, legacy fallback otherwise.
        """
        # Save to ChromaDB
        if self._vector_store:
            embedding = entry.embedding
            if embedding is not None:
                # Metadata without embedding (ChromaDB stores embedding separately)
                meta = {k: v for k, v in entry.metadata.items() if k != "embedding"}
                await self._vector_store.add(
                    entry_id=entry.id,
                    embedding=embedding.tolist(),
                    body=entry.body,
                    metadata=meta,
                )

        # Save to file
        if self._file_store:
            self._file_store.save(entry)
        else:
            # Legacy fallback: write .md file directly
            import json
            file_path = self.diary_dir / f"{entry.id}.md"
            content = f"```json\n{json.dumps(entry.metadata, indent=2)}\n```\n\n{entry.body}"
            file_path.write_text(content, encoding="utf-8")

        # Update cache
        if self._cache is not None:
            self._cache[entry.id] = entry

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding vector for text."""
        if self.openai:
            return await self.openai.embedding(text, model=self.embedding_model)
        else:
            raise RuntimeError("No OpenAI client available for embedding")

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        if a.size != b.size:
            raise ValueError(f"Vector size mismatch: {a.size} vs {b.size}")
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    # ── Phase 1: Legacy Migration ──────────────────────────────────────────

    async def _migrate_legacy_entries(self) -> int:
        """Migrate legacy .md diary entries to ChromaDB.

        Замечания 2, 3, 5:
        - Parses REAL C++ format (--- JSON front matter, camelCase metadata)
        - Preserves ALL usage stats (score, usageCount, lastUsed, confidence)
        - created_at = int(filename stem) for Unix timestamp ID (замечание 3)
        - visibility = "global" for all old entries (замечание 5, public by default)
        - Deletes .md file after successful ChromaDB migration (замечание 2)
        - Embedding from source JSON used if available; otherwise generated new

        Returns:
            Number of entries migrated
        """
        if not self._file_store or not self._vector_store:
            logger.info("Migration skipped: stores not configured")
            return 0

        # Per-entry migration: ChromaDB may already hold some entries (e.g.
        # created live by kunipy before the legacy .md files were copied in),
        # so a non-empty store must not skip the whole migration — otherwise
        # the migrated .md files stay invisible to RAG/consolidation.
        all_file_entries = self._file_store.load_all()
        if not all_file_entries:
            logger.info("Migration: no legacy entries found")
            return 0

        existing_ids = set(await self._vector_store.get_all_ids())
        entries = [e for e in all_file_entries if e.id not in existing_ids]
        if not entries:
            logger.info(
                f"Migration: {len(all_file_entries)} file entries already in ChromaDB"
            )
            return 0

        logger.info(
            f"Migrating {len(entries)}/{len(all_file_entries)} legacy entries to ChromaDB"
        )
        migrated = 0
        papik_chat_id = self.config.papik_chat_id

        for entry in entries:
            try:
                embedding = entry.embedding
                if embedding is None and entry.body.strip():
                    # Generate embedding if missing
                    try:
                        embedding = await self._get_embedding(entry.body)
                    except Exception:
                        logger.warning(
                            f"Cannot generate embedding for {entry.id}, skipping"
                        )
                        continue

                if embedding is None:
                    continue

                # Determine visibility (замечание 5)
                # Old entries default to global (public)
                visibility = "global"
                meta_chat_id = str(entry.metadata.get("chat_id", ""))
                if papik_chat_id and meta_chat_id == str(papik_chat_id):
                    visibility = "private"

                # Build metadata for ChromaDB (preserve all usage stats!)
                meta = {
                    "score": float(entry.metadata.get("score", 0.0)),
                    "confidence": float(entry.metadata.get("confidence", 0.0)),
                    "lastUsed": str(entry.metadata.get("lastUsed", "never")),
                    "usageCount": int(entry.metadata.get("usageCount", 0)),
                    "importance": float(entry.metadata.get("importance", 0.5)),
                    "kind": str(entry.metadata.get("kind", "other")),
                    "tags": str(entry.metadata.get("tags", "")),
                    "visibility": visibility,
                    "user_id": str(entry.metadata.get("user_id", "")),
                    "chat_id": meta_chat_id,
                    "sourceChannel": str(entry.metadata.get("sourceChannel", "")),
                    "created_at": int(entry.metadata.get("created_at", 0)),
                }

                # Preserve source_timestamp for audit
                source_ts = entry.metadata.get("source_timestamp", entry.id)
                if source_ts != entry.id:
                    meta["source_timestamp"] = str(source_ts)

                await self._vector_store.add(
                    entry_id=entry.id,
                    embedding=embedding.tolist(),
                    body=entry.body,
                    metadata=meta,
                )

                # Delete .md file after successful migration (замечание 2)
                self._file_store.delete(entry.id)
                migrated += 1

            except Exception:
                logger.exception(f"Failed to migrate entry {entry.id}")

        logger.info(f"Migration complete: {migrated}/{len(entries)} entries migrated")
        return migrated

    # ── Phase 2: Consolidation ─────────────────────────────────────────────

    def set_consolidation_service(self, service: Any) -> None:
        """Set the sleep consolidation service (Phase 2).

        Args:
            service: SleepConsolidationService instance
        """
        self._consolidation_service = service

    async def sleep_consolidation(self) -> None:
        """Perform nightly memory consolidation.

        Phase 2: Delegates to consolidation service when configured.
        Falls back to no-op with warning.
        """
        if self._consolidation_service:
            result = await self._consolidation_service.consolidate()
            logger.info(
                f"Consolidation: +{result.added} ~{result.updated} -{result.deleted}"
            )
        else:
            logger.warning("No consolidation service configured")

    # ── Phase 2: Entry management (for consolidation) ──────────────────────

    async def delete_entry(self, entry_id: str) -> None:
        """Delete a single diary entry from all stores (Phase 2).

        Args:
            entry_id: Entry identifier to delete
        """
        if self._vector_store:
            await self._vector_store.delete([entry_id])
        if self._file_store:
            self._file_store.delete(entry_id)
        if self._cache is not None:
            self._cache.pop(entry_id, None)

    async def get_all_entries(self) -> list[DiaryEntry]:
        """Return all diary entries (Phase 2).

        Returns:
            List of all DiaryEntry objects
        """
        if self._vector_store:
            rows = await self._vector_store.get()
            entries: list[DiaryEntry] = []
            for row in rows:
                meta = dict(row.get("metadata", {}))
                body = row.get("document", "")
                emb = row.get("embedding")
                if emb is not None:
                    meta["embedding"] = emb
                entries.append(DiaryEntry(id=row["id"], body=body, metadata=meta))
            return entries
        cache = await self._load_cache()
        return list(cache.values())

    # ── Phase 6: Text Search (for CLI) ─────────────────────────────────────

    async def search_by_text(
        self,
        query: str,
        max_entries: int = 10,
    ) -> list[tuple[DiaryEntry, float]]:
        """Full-text search across diary entry bodies and tags.

        Used by diary_cli for --text and --tags search modes.

        Args:
            query: Search query (substring or #hashtag)
            max_entries: Maximum results

        Returns:
            List of (entry, score) tuples, sorted by relevance
        """
        cache = await self._load_cache()
        results: list[tuple[DiaryEntry, float]] = []

        query_lower = query.lower()
        is_hashtag = query.startswith("#")

        for entry in cache.values():
            score = 0.0
            body_lower = entry.body.lower()
            tags = str(entry.metadata.get("tags", "")).lower()

            if is_hashtag:
                # Tag search: exact tag match
                tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
                if query_lower in tag_set:
                    score = 1.0
                elif query_lower in body_lower:
                    score = 0.5
            else:
                # Substring search
                if query_lower in body_lower:
                    # Score by occurrence count
                    count = body_lower.count(query_lower)
                    score = min(1.0, count / 5.0)
                elif query_lower in tags:
                    score = 0.7

            if score > 0:
                # Boost by importance
                importance = float(entry.metadata.get("importance", 0.5))
                final_score = score * 0.8 + importance * 0.2
                results.append((entry, final_score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_entries]

    async def get_entry(self, entry_id: str) -> DiaryEntry | None:
        """Retrieve a single diary entry by ID.

        Args:
            entry_id: Entry identifier

        Returns:
            DiaryEntry or None
        """
        # Try cache first
        if self._cache is not None and entry_id in self._cache:
            return self._cache[entry_id]

        # Try file store
        if self._file_store:
            return self._file_store.load(entry_id)

        # Legacy: read file directly
        file_path = self.diary_dir / f"{entry_id}.md"
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            return DiaryEntry.from_file_content(entry_id, content)
        return None

    async def count(self) -> int:
        """Return total number of diary entries."""
        if self._vector_store:
            return await self._vector_store.count()
        cache = await self._load_cache()
        return len(cache)
