"""Memory bridge interface (ТЗ-004).

Contract for desktop ↔ memory integration. Desktop package depends on
this Protocol, not on concrete Diary/MemoryService implementations.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryBridge(Protocol):
    """Interface for memory operations from desktop."""

    async def recall(self, text: str) -> str:
        """Retrieve relevant memories for given text.

        Args:
            text: Query text (e.g. user message)

        Returns:
            Formatted memory context or empty string
        """
        ...

    async def remember(self, text: str) -> None:
        """Store text as a memory entry.

        Args:
            text: Content to remember
        """
        ...


class NoOpMemoryBridge:
    """No-op stub: does nothing, returns empty strings."""

    async def recall(self, text: str) -> str:
        """Return empty string (no memories)."""
        return ""

    async def remember(self, text: str) -> None:
        """Do nothing."""
