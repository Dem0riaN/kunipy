"""ChromaDB vector store wrapper (ТЗ-002 punkt 38)."""

import logging
from datetime import datetime
from typing import Any

import chromadb
from chromadb.config import Settings

from ...interfaces.memory import MemoryKind, MemoryPiece, MemoryScope

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB wrapper for memory storage."""

    def __init__(self, persist_directory: str = "./data/chroma"):
        """Initialize ChromaDB client.

        Args:
            persist_directory: Path to persist ChromaDB data
        """
        self._client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False,
        ))
        self._collection = self._client.get_or_create_collection(
            name="kunipy_memory",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Initialized VectorStore at {persist_directory}")

    async def add_memory(self, piece: MemoryPiece) -> None:
        """Add memory piece to vector store.

        Args:
            piece: Memory piece to store
        """
        metadata = {
            "kind": piece.kind.value,
            "confidence": piece.confidence,
            "importance": piece.importance,
            "created_at": piece.created_at.isoformat(),
            "updated_at": piece.updated_at.isoformat(),
            "last_used": piece.last_used.isoformat(),
            "usage_count": piece.usage_count,
            "scope": piece.scope.value,
            "user_id": piece.user_id or "",
            "chat_id": piece.chat_id or "",
            "channel": piece.channel or "",
            "source_type": piece.source_type or "",
        }

        self._collection.add(
            ids=[piece.id],
            embeddings=[piece.embedding],
            documents=[piece.content],
            metadatas=[metadata]
        )

    async def get_memory(self, memory_id: str) -> MemoryPiece | None:
        """Retrieve memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory piece if found
        """
        result = self._collection.get(
            ids=[memory_id],
            include=["embeddings", "documents", "metadatas"]
        )

        if not result["ids"]:
            return None

        return self._result_to_memory(
            result["ids"][0],
            result["embeddings"][0],
            result["documents"][0],
            result["metadatas"][0]
        )

    async def update_memory(self, piece: MemoryPiece) -> None:
        """Update existing memory piece.

        Args:
            piece: Updated memory piece
        """
        metadata = {
            "kind": piece.kind.value,
            "confidence": piece.confidence,
            "importance": piece.importance,
            "updated_at": piece.updated_at.isoformat(),
            "last_used": piece.last_used.isoformat(),
            "usage_count": piece.usage_count,
            "scope": piece.scope.value,
        }

        self._collection.update(
            ids=[piece.id],
            embeddings=[piece.embedding],
            documents=[piece.content],
            metadatas=[metadata]
        )

    async def delete_memory(self, memory_id: str) -> None:
        """Delete memory piece.

        Args:
            memory_id: Memory ID
        """
        self._collection.delete(ids=[memory_id])

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        where: dict[str, Any] | None = None
    ) -> list[MemoryPiece]:
        """Search by embedding similarity with optional filters.

        Args:
            query_embedding: Query vector
            limit: Maximum results
            where: Metadata filters (ChromaDB where clause)

        Returns:
            Ranked list of memory pieces
        """
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["embeddings", "documents", "metadatas", "distances"]
        )

        if not result["ids"] or not result["ids"][0]:
            return []

        memories = []
        for i in range(len(result["ids"][0])):
            memory = self._result_to_memory(
                result["ids"][0][i],
                result["embeddings"][0][i],
                result["documents"][0][i],
                result["metadatas"][0][i]
            )
            memories.append(memory)

        return memories

    async def count(self, where: dict[str, Any] | None = None) -> int:
        """Count memories matching filter.

        Args:
            where: Metadata filters

        Returns:
            Count of matching memories
        """
        if where:
            _ = self._collection.get(where=where, limit=1)
            return self._collection.count()
        return self._collection.count()

    def _result_to_memory(
        self,
        memory_id: str,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any]
    ) -> MemoryPiece:
        """Convert ChromaDB result to MemoryPiece.

        Args:
            memory_id: Memory ID
            embedding: Embedding vector
            document: Text content
            metadata: Metadata dict

        Returns:
            MemoryPiece instance
        """
        return MemoryPiece(
            id=memory_id,
            kind=MemoryKind(metadata.get("kind", "other")),
            content=document,
            confidence=metadata.get("confidence", 0.0),
            importance=metadata.get("importance", 0.5),
            created_at=datetime.fromisoformat(metadata["created_at"]),
            updated_at=datetime.fromisoformat(metadata["updated_at"]),
            last_used=datetime.fromisoformat(metadata["last_used"]),
            usage_count=metadata.get("usage_count", 0),
            embedding=embedding,
            scope=MemoryScope(metadata.get("scope", "private")),
            user_id=metadata.get("user_id") or None,
            chat_id=metadata.get("chat_id") or None,
            channel=metadata.get("channel") or None,
            source_type=metadata.get("source_type") or None,
        )
