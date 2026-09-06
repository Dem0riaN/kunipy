"""Working memory for kunipy.

Stores short-term context across messages in a conversation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkingMemoryEntry:
    """An entry in working memory."""

    key: str
    value: Any
    timestamp: float
    ttl: Optional[float] = None  # seconds, None = no expiration


class WorkingMemory:
    """In-memory short-term storage for conversation context.

    Provides key-value storage with optional TTL.
    """

    def __init__(self, default_ttl: float = 3600):
        self._store: Dict[str, WorkingMemoryEntry] = {}
        self._default_ttl = default_ttl

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store a value in working memory."""
        if ttl is None:
            ttl = self._default_ttl
        entry = WorkingMemoryEntry(
            key=key,
            value=value,
            timestamp=time.time(),
            ttl=ttl,
        )
        self._store[key] = entry
        logger.debug(f"Working memory set {key} = {value}")

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from working memory."""
        entry = self._store.get(key)
        if entry is None:
            return None
        # Check expiration
        if entry.ttl is not None:
            now = time.time()
            if now - entry.timestamp > entry.ttl:
                del self._store[key]
                return None
        return entry.value

    def delete(self, key: str) -> None:
        """Delete a value from working memory."""
        if key in self._store:
            del self._store[key]
            logger.debug(f"Working memory deleted {key}")

    def clear(self) -> None:
        """Clear all entries."""
        self._store.clear()
        logger.debug("Working memory cleared")

    def list_keys(self) -> List[str]:
        """Return all keys."""
        return list(self._store.keys())

    def get_all(self) -> Dict[str, Any]:
        """Return all non-expired key-value pairs."""
        result = {}
        for key in list(self._store.keys()):
            val = self.get(key)
            if val is not None:
                result[key] = val
        return result

    def update(self, key: str, value: Any) -> None:
        """Update an existing entry (refresh TTL)."""
        if key in self._store:
            self.set(key, value, self._store[key].ttl)
        else:
            self.set(key, value)


# Singleton instance
_memory: Optional[WorkingMemory] = None


def get_working_memory() -> WorkingMemory:
    """Get global working memory instance."""
    global _memory
    if _memory is None:
        _memory = WorkingMemory()
    return _memory
