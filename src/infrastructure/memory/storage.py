"""MemoryStore implementation with ChromaDB backend (ТЗ-002 punkt 38)."""

import logging
from datetime import UTC, datetime

from ...interfaces.memory import IMemoryStore, MemoryPiece, MemoryScope
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryStore(IMemoryStore):
    """Long-term memory storage with semantic search."""

    def __init__(self, persist_directory: str = "./data/chroma"):
        """Initialize memory store.

        Args:
            persist_directory: Path to persist ChromaDB data
        """
        self._store = VectorStore(persist_directory)
        logger.info("Initialized MemoryStore")

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Create new memory piece.

        Args:
            piece: Memory piece to store

        Returns:
            Memory ID
        """
        await self._store.add_memory(piece)
        logger.debug(f"Created memory {piece.id} ({piece.kind.value})")
        return piece.id

    async def get_memory(self, memory_id: str) -> MemoryPiece | None:
        """Retrieve memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory piece if found
        """
        return await self._store.get_memory(memory_id)

    async def update_memory(self, piece: MemoryPiece) -> bool:
        """Update existing memory piece.

        Args:
            piece: Updated memory piece

        Returns:
            True if successful
        """
        try:
            piece.updated_at = datetime.now(UTC)
            await self._store.update_memory(piece)
            logger.debug(f"Updated memory {piece.id}")
            return True
        except (ValueError, KeyError, TypeError, RuntimeError):
            logger.exception(f"Failed to update memory {piece.id}")
            return False

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory piece.

        Args:
            memory_id: Memory ID

        Returns:
            True if deleted
        """
        try:
            await self._store.delete_memory(memory_id)
            logger.debug(f"Deleted memory {memory_id}")
            return True
        except (ValueError, KeyError, TypeError, RuntimeError):
            logger.exception(f"Failed to delete memory {memory_id}")
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

        Implements semantic search with scope filtering.

        Args:
            query_embedding: Query vector
            scope: Memory scope filter
            user_id: Filter by user
            chat_id: Filter by chat
            limit: Maximum results
            min_confidence: Minimum confidence threshold

        Returns:
            Ranked list of memory pieces
        """
        where: dict[str, str | float] = {"scope": scope.value}

        if user_id:
            where["user_id"] = user_id
        if chat_id:
            where["chat_id"] = chat_id
        if min_confidence > -1.0:
            where["confidence"] = {"$gte": min_confidence}

        memories = await self._store.search(
            query_embedding=query_embedding,
            limit=limit,
            where=where
        )

        # Update usage stats
        now = datetime.now(UTC)
        for memory in memories:
            memory.last_used = now
            memory.usage_count += 1
            await self._store.update_memory(memory)

        return memories

    async def search_by_user(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search user-specific memory.

        Args:
            user_id: User ID
            query_embedding: Query vector
            limit: Maximum results

        Returns:
            Ranked list of user memories
        """
        return await self.search_memory(
            query_embedding=query_embedding,
            scope=MemoryScope.USER,
            user_id=user_id,
            limit=limit
        )

    async def search_by_chat(
        self,
        chat_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search chat-specific memory.

        Args:
            chat_id: Chat ID
            query_embedding: Query vector
            limit: Maximum results

        Returns:
            Ranked list of chat memories
        """
        return await self.search_memory(
            query_embedding=query_embedding,
            scope=MemoryScope.CHAT,
            chat_id=chat_id,
            limit=limit
        )
