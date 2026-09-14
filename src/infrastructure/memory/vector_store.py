"""ChromaDB vector store wrapper (ТЗ-002 punkt 38)."""

import json
import logging
from datetime import UTC, datetime
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

        Persists all MemoryPiece fields. Lists are JSON-serialized
        because ChromaDB metadata only supports str/int/float/bool.

        Args:
            piece: Memory piece to store
        """
        metadata = self._piece_to_metadata(piece)

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

        Reads current document first to merge metadata and avoid
        losing fields that ChromaDB would otherwise overwrite entirely.

        Args:
            piece: Updated memory piece
        """
        current = self._collection.get(
            ids=[piece.id],
            include=["documents", "metadatas"]
        )
        if not current["ids"]:
            raise ValueError(f"Memory {piece.id} not found in vector store")

        old_metadata = current["metadatas"][0] or {}

        # Merge: start from old, overlay new values from piece
        metadata = {
            **old_metadata,
            **self._piece_to_metadata(piece),
        }

        embedding_arg = [piece.embedding] if (piece.embedding is not None and len(piece.embedding) > 0) else None

        self._collection.update(
            ids=[piece.id],
            embeddings=embedding_arg,
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
            result = self._collection.get(where=where)
            return len(result["ids"])
        return self._collection.count()

    async def batch_update_usage(
        self,
        ids: list[str],
        last_used: datetime,
        usage_counts: list[int],
    ) -> None:
        """Batch-update usage stats for multiple memories (fire-and-forget).

        Avoids N+1 writes during search_memory() — all updates go in one
        ChromaDB call instead of one-per-result.

        Args:
            ids: Memory IDs to update
            last_used: Shared last_used timestamp
            usage_counts: Per-memory new usage count (same order as ids)
        """
        if not ids:
            return

        last_used_iso = last_used.isoformat()
        metadatas = []
        for uid, count in zip(ids, usage_counts, strict=True):
            current = self._collection.get(ids=[uid], include=["metadatas"])
            if not current["ids"]:
                continue
            md = current["metadatas"][0] or {}
            md["last_used"] = last_used_iso
            md["usage_count"] = count
            metadatas.append(md)

        if metadatas:
            self._collection.update(ids=ids, metadatas=metadatas)

    @staticmethod
    def _piece_to_metadata(piece: MemoryPiece) -> dict[str, Any]:
        """Serialize MemoryPiece fields to ChromaDB-safe metadata.

        Lists/dicts are JSON-serialized; ChromaDB only accepts
        str/int/float/bool values.
        """
        return {
            "kind": piece.kind.value,
            "confidence": piece.confidence,
            "importance": piece.importance,
            "created_at": piece.created_at.isoformat(),
            "updated_at": piece.updated_at.isoformat(),
            "last_used": piece.last_used.isoformat() if piece.last_used else "",
            "usage_count": piece.usage_count,
            "scope": piece.scope.value,
            "user_id": piece.user_id or "",
            "chat_id": piece.chat_id or "",
            "channel": piece.channel or "",
            "source_type": piece.source_type or "",
            "source_message_ids": json.dumps(piece.source_message_ids or []),
            "retrieval_cues": json.dumps(piece.retrieval_cues or []),
            "entities": json.dumps(piece.entities or []),
            "metadata_json": json.dumps(piece.metadata or {}),
        }

    @staticmethod
    def _result_to_memory(
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
        created_at_str = metadata.get("created_at")
        updated_at_str = metadata.get("updated_at")
        last_used_str = metadata.get("last_used")
        now = datetime.now(UTC)

        return MemoryPiece(
            id=memory_id,
            kind=MemoryKind(metadata.get("kind", "other")),
            content=document,
            confidence=metadata.get("confidence", 0.0),
            importance=metadata.get("importance", 0.5),
            created_at=datetime.fromisoformat(created_at_str) if created_at_str else now,
            updated_at=datetime.fromisoformat(updated_at_str) if updated_at_str else now,
            last_used=datetime.fromisoformat(last_used_str) if last_used_str else now,
            usage_count=metadata.get("usage_count", 0),
            embedding=embedding,
            scope=MemoryScope(metadata.get("scope", "private")),
            user_id=metadata.get("user_id") or None,
            chat_id=metadata.get("chat_id") or None,
            channel=metadata.get("channel") or None,
            source_type=metadata.get("source_type") or None,
            source_message_ids=json.loads(metadata.get("source_message_ids", "[]")) if metadata.get("source_message_ids") else [],
            retrieval_cues=json.loads(metadata.get("retrieval_cues", "[]")) if metadata.get("retrieval_cues") else [],
            entities=json.loads(metadata.get("entities", "[]")) if metadata.get("entities") else [],
            metadata=json.loads(metadata.get("metadata_json", "{}")) if metadata.get("metadata_json") else {},
        )
