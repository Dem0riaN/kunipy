"""Embedding cache layer (ТЗ-002 optimization)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """In-memory cache for embeddings to reduce API calls."""

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize embedding cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
        """
        self._cache: dict[str, tuple[list[float], datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0
        logger.info(f"Initialized EmbeddingCache with TTL={ttl_seconds}s")

    def get(self, text: str) -> list[float] | None:
        """Get cached embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector if cached and not expired, None otherwise
        """
        if text not in self._cache:
            self._misses += 1
            return None

        embedding, timestamp = self._cache[text]
        if datetime.now(UTC) - timestamp > self._ttl:
            # Expired
            del self._cache[text]
            self._misses += 1
            return None

        self._hits += 1
        return embedding

    def set(self, text: str, embedding: list[float]) -> None:
        """Store embedding in cache.

        Args:
            text: Input text
            embedding: Embedding vector
        """
        self._cache[text] = (embedding, datetime.now(UTC))

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.debug("Cleared embedding cache")

    def evict_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries evicted
        """
        now = datetime.now(UTC)
        expired = [
            text for text, (_, timestamp) in self._cache.items()
            if now - timestamp > self._ttl
        ]
        for text in expired:
            del self._cache[text]

        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")
        return len(expired)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "hit_rate": hit_rate,
        }
