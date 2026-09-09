"""Diary memory system with dependency injection.

Refactored version that accepts config explicitly instead of using singleton.
Based on ТЗ-001 punkt 6 (dependency injection).
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

import numpy as np

from .config import Config
from .openai_chat import OpenAIChat

logger = logging.getLogger(__name__)


@dataclass
class DiaryEntry:
    """A single diary entry with metadata."""
    id: str
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def embedding(self) -> Optional[np.ndarray]:
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
        """Parse diary entry from file content."""
        # Simple parser - extract metadata and body
        # (Implementation from original diary.py)
        metadata = {}
        body = content

        # Try to extract JSON metadata block if present
        if content.startswith("```json"):
            end_idx = content.find("```", 7)
            if end_idx > 0:
                import json
                try:
                    metadata = json.loads(content[7:end_idx])
                    body = content[end_idx + 3:].strip()
                except json.JSONDecodeError:
                    pass

        return DiaryEntry(id=file_id, text=content, metadata=metadata, body=body)


class Diary:
    """Diary memory system with explicit config dependency.

    REFACTORED: Accepts Config via constructor instead of get_config() singleton.
    """

    def __init__(
        self,
        diary_dir: str | Path,
        openai_chat: OpenAIChat,
        config: Config,
        embedding_model: Optional[str] = None,
    ):
        """Initialize diary with dependencies.

        Args:
            diary_dir: Directory for diary entries
            openai_chat: OpenAI client for embeddings
            config: Application configuration
            embedding_model: Override embedding model (optional)
        """
        self.diary_dir = Path(diary_dir)
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.openai = openai_chat
        self.config = config  # Store config for settings access
        self.embedding_model = embedding_model or config.embedding.model
        self._cache: Optional[Dict[str, DiaryEntry]] = None
        self._lock = asyncio.Lock()

    async def _load_cache(self) -> Dict[str, DiaryEntry]:
        """Lazy load all diary entries into memory."""
        if self._cache is not None:
            return self._cache

        async with self._lock:
            if self._cache is not None:
                return self._cache

            cache = {}
            for file_path in self.diary_dir.glob("*.md"):
                file_id = file_path.stem
                try:
                    content = file_path.read_text(encoding="utf-8")
                    entry = DiaryEntry.from_file_content(file_id, content)
                    cache[file_id] = entry
                except Exception as e:
                    logger.error(f"Failed to load diary entry {file_id}: {e}")

            self._cache = cache
            logger.info(f"Loaded {len(cache)} diary entries")
            return cache

    async def query(
        self,
        query_vector: np.ndarray,
        max_entries: int = 5,
        confidence_factor: float = 0.01,
        min_relatedness: Optional[float] = None,
        filter_fn: Optional[Callable[[DiaryEntry], bool]] = None,
    ) -> List[tuple[DiaryEntry, float]]:
        """Query diary entries by embedding similarity.

        REFACTORED: Uses self.config instead of get_config().
        """
        if min_relatedness is None:
            min_relatedness = self.config.diary_min_relatedness

        cache = await self._load_cache()
        results = []

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

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_entries]

    async def add_entry(self, text: str, confidence: float = 0.0) -> str:
        """Add a new diary entry with optional embedding.

        REFACTORED: Uses self.config instead of get_config().
        """
        threshold = self.config.diary_plagiarism_threshold

        if confidence < 0.5:
            # Check for duplicates
            embedding = await self._get_embedding(text)
            existing = await self.query(embedding, max_entries=1, min_relatedness=threshold)
            if existing:
                logger.info(f"Skipping duplicate diary entry (similarity {existing[0][1]:.3f})")
                return existing[0][0].id

        # Create new entry
        entry_id = f"entry_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        entry = DiaryEntry(
            id=entry_id,
            body=text,
            metadata={
                "confidence": confidence,
                "last_used": datetime.now().isoformat(),
                "usage_count": 0,
            }
        )
        entry.embedding = await self._get_embedding(text)
        await self.save(entry)
        logger.info(f"Added diary entry {entry_id}")
        return entry_id

    async def save(self, entry: DiaryEntry) -> None:
        """Save diary entry to disk."""
        file_path = self.diary_dir / f"{entry.id}.md"

        # Serialize metadata + body
        import json
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

    async def sleep_consolidation(self) -> None:
        """Perform nightly memory consolidation.

        Placeholder for future implementation of memory compression.
        """
        logger.info("Sleep consolidation started (placeholder)")
        # TODO: Implement memory consolidation logic
        logger.info("Sleep consolidation completed")
