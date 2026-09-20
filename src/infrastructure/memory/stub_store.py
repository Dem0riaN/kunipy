"""Stub memory store implementation.

Temporary in-memory implementation until Phase 2.
Implements IMemoryStore protocol with minimal functionality.
"""

from datetime import UTC, datetime

from ...domain.memory.models import MemoryPiece, WorkingMemoryContext
from ...interfaces.memory import MemoryScope


class InMemoryStore:
    """Stub in-memory memory store.

    This is a temporary implementation for Phase 1.
    Full implementation in Phase 2 will use proper vector database.
    """

    def __init__(self):
        self._memories: dict[str, MemoryPiece] = {}

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Store memory piece in memory."""
        self._memories[piece.id] = piece
        return piece.id

    async def get_memory(self, memory_id: str) -> MemoryPiece | None:
        """Retrieve memory by ID."""
        return self._memories.get(memory_id)

    async def update_memory(self, piece: MemoryPiece) -> bool:
        """Update existing memory."""
        if piece.id in self._memories:
            self._memories[piece.id] = piece
            return True
        return False

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory."""
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    async def search_memory(
        self,
        query_embedding: list[float],
        scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 10,
        min_confidence: float = -1.0
    ) -> list[MemoryPiece]:
        """Search memory by embedding similarity.

        Stub implementation: returns empty list.
        Full vector search implementation in Phase 2.
        """
        return []

    async def search_by_user(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search user-specific memory."""
        return []

    async def search_by_chat(
        self,
        chat_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search chat-specific memory."""
        return []


class InMemoryWorkingMemory:
    """Stub in-memory working memory.

    Temporary implementation for Phase 1.
    Full implementation in Phase 2 with proper lifecycle management.
    """

    def __init__(self):
        self._contexts: dict[tuple[str, str], WorkingMemoryContext] = {}

    def _key(self, user_id: str, chat_id: str) -> tuple[str, str]:
        """Create context key."""
        return (user_id, chat_id)

    async def get_context(
        self,
        user_id: str,
        chat_id: str
    ) -> WorkingMemoryContext:
        """Get or create working memory context."""
        key = self._key(user_id, chat_id)
        if key not in self._contexts:
            self._contexts[key] = WorkingMemoryContext(
                user_id=user_id,
                chat_id=chat_id,
                channel="telegram",  # Default
                last_interaction=datetime.now(UTC)
            )
        return self._contexts[key]

    async def update_context(
        self,
        user_id: str,
        chat_id: str,
        updates: dict
    ) -> None:
        """Update working memory context."""
        context = await self.get_context(user_id, chat_id)
        for key, value in updates.items():
            if hasattr(context, key):
                setattr(context, key, value)

    async def add_promise(
        self,
        user_id: str,
        chat_id: str,
        promise: str
    ) -> None:
        """Add promise to working memory."""
        context = await self.get_context(user_id, chat_id)
        from ...domain.memory.models import Promise
        context.promises.append(
            Promise(
                id=f"promise_{len(context.promises)}",
                content=promise,
                to_user_id=user_id,
                created_at=datetime.now(UTC)
            )
        )

    async def add_plan(
        self,
        user_id: str,
        chat_id: str,
        plan: dict
    ) -> None:
        """Add plan to working memory."""
        context = await self.get_context(user_id, chat_id)
        from ...domain.memory.models import Plan
        context.plans.append(
            Plan(
                id=f"plan_{len(context.plans)}",
                description=plan.get("description", ""),
                steps=plan.get("steps", []),
                created_at=datetime.now(UTC)
            )
        )

    async def clear_context(
        self,
        user_id: str,
        chat_id: str
    ) -> None:
        """Clear working memory for context."""
        key = self._key(user_id, chat_id)
        if key in self._contexts:
            del self._contexts[key]
