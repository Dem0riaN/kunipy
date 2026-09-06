"""Diary memory system for kunipy.

Stores entries as markdown files with YAML metadata, provides RAG search via embeddings,
and performs sleep consolidation (memory compression).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Callable

import numpy as np

from .config import get_config
from .openai_chat import OpenAIChat, Message

logger = logging.getLogger(__name__)


@dataclass
class DiaryEntry:
    """A single diary entry with metadata."""
    id: str  # filename without .md
    text: str = ""  # full raw content (metadata + body)
    metadata: Dict[str, Any] = field(default_factory=dict)
    body: str = ""  # freeform text without metadata block

    @property
    def embedding(self) -> Optional[np.ndarray]:
        """Get the embedding vector from metadata."""
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

    @confidence.setter
    def confidence(self, value: float) -> None:
        self.metadata["confidence"] = value

    @property
    def score(self) -> float:
        return self.metadata.get("score", 0.0)

    @score.setter
    def score(self, value: float) -> None:
        self.metadata["score"] = value

    @property
    def last_used(self) -> str:
        return self.metadata.get("last_used", "never")

    @last_used.setter
    def last_used(self, value: str) -> None:
        self.metadata["last_used"] = value

    @property
    def usage_count(self) -> int:
        return self.metadata.get("usage_count", 0)

    @usage_count.setter
    def usage_count(self, value: int) -> None:
        self.metadata["usage_count"] = value

    def increment_usage(self) -> None:
        self.usage_count += 1
        self.last_used = datetime.now().isoformat()

    def to_file_content(self) -> str:
        """Serialize entry to markdown with metadata block."""
        # Build metadata JSON
        meta = self.metadata.copy()
        # Remove embedding from metadata block to keep files readable
        # (it's still stored, but we can omit it for readability)
        # Actually we keep it but it's large, but we want to preserve it
        meta_for_file = {k: v for k, v in meta.items() if k != "embedding"}
        # Store embedding separately as a compact representation? We'll keep it.
        meta_for_file = meta.copy()
        meta_json = json.dumps(meta_for_file, indent=2, ensure_ascii=False)
        return f"---\n{meta_json}\n---\n\n{self.body}"

    @classmethod
    def from_file_content(cls, file_id: str, content: str) -> DiaryEntry:
        """Parse markdown file content into DiaryEntry."""
        metadata = {}
        body = content
        # Try to extract YAML/JSON metadata block between --- delimiters
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if match:
            meta_str = match.group(1)
            body = match.group(2)
            try:
                metadata = json.loads(meta_str)
            except json.JSONDecodeError:
                # Try to handle as YAML? For now just ignore
                pass
        return cls(
            id=file_id,
            text=content,
            metadata=metadata,
            body=body.strip()
        )


class Diary:
    """Diary memory system with RAG and sleep consolidation."""

    def __init__(
        self,
        diary_dir: str | Path,
        openai: Optional[OpenAIChat] = None,
        embedding_model: Optional[str] = None,
    ):
        self.diary_dir = Path(diary_dir)
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.openai = openai or OpenAIChat()
        self.embedding_model = embedding_model
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
                    logger.warning(f"Failed to load diary entry {file_path}: {e}")
            self._cache = cache
            return self._cache

    async def save(self, entry: DiaryEntry) -> None:
        """Save a diary entry to disk and update cache."""
        cache = await self._load_cache()
        file_path = self.diary_dir / f"{entry.id}.md"
        content = entry.to_file_content()
        file_path.write_text(content, encoding="utf-8")
        cache[entry.id] = entry
        logger.debug(f"Saved diary entry {entry.id}")

    async def delete(self, entry_id: str) -> None:
        """Delete a diary entry from disk and cache."""
        cache = await self._load_cache()
        file_path = self.diary_dir / f"{entry_id}.md"
        if file_path.exists():
            file_path.unlink()
        if entry_id in cache:
            del cache[entry_id]
        logger.debug(f"Deleted diary entry {entry_id}")

    async def get_all(self) -> List[DiaryEntry]:
        """Get all diary entries, newest first."""
        cache = await self._load_cache()
        entries = list(cache.values())
        # Sort by ID descending (assuming IDs are timestamps or incrementing)
        entries.sort(key=lambda e: e.id, reverse=True)
        return entries

    async def get(self, entry_id: str) -> Optional[DiaryEntry]:
        """Get a single diary entry by ID."""
        cache = await self._load_cache()
        return cache.get(entry_id)

    async def query(
        self,
        query_vector: np.ndarray,
        max_entries: int = 10,
        confidence_factor: float = 0.01,
        min_relatedness: Optional[float] = None,
        filter_fn: Optional[Callable[[DiaryEntry], bool]] = None,
    ) -> List[tuple[DiaryEntry, float]]:
        """ diary entries by embedding similarity."""
        config = get_config()
        if min_relatedness is None:
            min_relatedness = config.diary_min_relatedness

        cache = await self._load_cache()
        results = []

        for entry in cache.values():
            if filter_fn and not filter_fn(entry):
                continue
            # Get or compute embedding
            embedding = entry.embedding
            if embedding is None:
                # Generate embedding on the fly
                embedding = await self._get_embedding(entry.body)
                entry.embedding = embedding
                await self.save(entry)
            # Compute cosine similarity
            similarity = self._cosine_similarity(query_vector, embedding)
            # Normalize to [0, 1]
            normalized = (similarity + 1.0) / 2.0
            # Adjust with confidence
            final_score = normalized + entry.confidence * confidence_factor
            # Clamp to [0, 1]
            final_score = max(0.0, min(1.0, final_score))
            if final_score >= min_relatedness:
                results.append((entry, final_score))

        # Sort by score descending and truncate
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_entries]

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

    async def sleep_consolidation(
        self,
        max_sleep_time: int = 6 * 3600,  # 6 hours in seconds
        recent_bias: float = 0.8,
    ) -> None:
        """Simulate sleep: consolidate and compress diary entries."""
        logger.info("Starting sleep consolidation...")
        cache = await self._load_cache()
        if not cache:
            logger.info("Diary is empty, skipping sleep")
            return

        entries = list(cache.values())
        entries.sort(key=lambda e: e.id, reverse=True)  # newest first

        start_time = datetime.now()
        elapsed = timedelta(0)
        processed_ids: Set[str] = set()

        while elapsed.total_seconds() < max_sleep_time and entries:
            # Select target entry
            if random.random() < recent_bias:
                # Pick the most recent entry (first in list)
                target = entries.pop(0)
            else:
                # Pick random entry
                idx = random.randint(0, len(entries) - 1)
                target = entries.pop(idx)

            if target.id in processed_ids:
                continue

            # Get embedding for target
            if target.embedding is None:
                target.embedding = await self._get_embedding(target.body)
                await self.save(target)

            # Find related entries
            related = await self.query(
                target.embedding,
                max_entries=5,
                min_relatedness=0.5,
                filter_fn=lambda e: e.id != target.id and e.id not in processed_ids
            )

            # Collect entries to merge (target + related)
            to_merge = [target] + [e for e, score in related if e.id not in processed_ids]
            if len(to_merge) < 2:
                # Not enough related entries, just skip
                processed_ids.add(target.id)
                continue

            # Ask LLM to consolidate
            consolidated = await self._consolidate_entries(to_merge)
            if consolidated:
                # Delete old entries
                for old_entry in to_merge:
                    await self.delete(old_entry.id)
                # Save new consolidated entries
                for new_entry in consolidated:
                    await self.save(new_entry)
                    processed_ids.add(new_entry.id)
            else:
                processed_ids.add(target.id)

            # Update elapsed time
            elapsed = datetime.now() - start_time

        logger.info(f"Sleep consolidation completed after {elapsed.total_seconds():.0f}s")
        # Reload cache to reflect changes
        self._cache = None

    async def _consolidate_entries(
        self,
        entries: List[DiaryEntry],
    ) -> List[DiaryEntry]:
        """Use LLM to consolidate multiple diary entries into one or more compressed entries."""
        if not entries:
            return []

        # Build prompt for consolidation
        prompt = """You are consolidating diary entries to reduce redundancy while preserving key information.
Given the following entries, merge them into a single cohesive entry (or multiple if they cover distinct topics).
For each output entry, start with a metadata line: `---{"confidence": X}---` where X is a number between -1 and 1.
Then write the consolidated text.

Entries to consolidate:
"""
        for i, entry in enumerate(entries):
            prompt += f"\n--- Entry {i+1} (confidence: {entry.confidence}) ---\n{entry.body}\n"

        prompt += "\nOutput consolidated entries (use the format described above):\n"

        messages = [Message(role="user", content=prompt)]
        system_prompt = "You are a memory consolidation assistant. Keep essential facts, emotions, and context. Remove redundancy."

        try:
            response = await self.openai.chat(
                messages,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=2000,
            )
            if not response.choices:
                logger.warning("No response from LLM for consolidation")
                return []
            content = response.choices[0].get("message", {}).get("content", "")
            # Parse output into entries
            return self._parse_consolidated_output(content)
        except Exception as e:
            logger.error(f"Error during consolidation: {e}")
            return []

    def _parse_consolidated_output(self, content: str) -> List[DiaryEntry]:
        """Parse LLM output into DiaryEntry objects."""
        entries = []
        # Split by --- separators
        parts = re.split(r"---\s*\n?", content)
        # Each part should be a metadata line followed by text
        metadata = {}
        body_parts = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Try to parse JSON if it looks like a metadata block
            if part.startswith("{") and part.endswith("}"):
                try:
                    metadata = json.loads(part)
                    continue
                except json.JSONDecodeError:
                    pass
            # Otherwise treat as body text
            body_parts.append(part)

        if not body_parts:
            return []

        body = "\n\n".join(body_parts)
        entry_id = f"consolidated_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        entry = DiaryEntry(
            id=entry_id,
            body=body,
            metadata=metadata,
        )
        # Ensure confidence is set
        if "confidence" not in entry.metadata:
            entry.metadata["confidence"] = 0.0
        entries.append(entry)
        return entries

    async def add_entry(self, text: str, confidence: float = 0.0) -> str:
        """Add a new diary entry with optional embedding."""
        # Check for duplicate (plagiarism) if confidence is low
        config = get_config()
        threshold = config.diary_plagiarism_threshold
        if confidence < 0.5:  # only check low-confidence entries to avoid blocking important facts
            # Generate embedding for new text
            embedding = await self._get_embedding(text)
            # Check against existing entries
            existing = await self.query(embedding, max_entries=1, min_relatedness=threshold)
            if existing:
                # Too similar, skip
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
        # Generate embedding
        entry.embedding = await self._get_embedding(text)
        await self.save(entry)
        logger.info(f"Added diary entry {entry_id}")
        return entry_id
