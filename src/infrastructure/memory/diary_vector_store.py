"""ChromaDB vector store for diary entries (Phase 1).

Separate from VectorStore (vector_store.py) which is tied to MemoryPiece (ТЗ-002).
Diary entries use a different metadata schema aligned with C++ kuni format.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class DiaryVectorStore:
    """ChromaDB wrapper for diary entries (C++ kuni format).

    Metadata schema (C++ format + ТЗ-002 extensions):
        score, confidence, lastUsed, usageCount, importance, kind, tags,
        visibility, user_id, chat_id, source_channel, created_at, source_timestamp
    """

    def __init__(
        self,
        persist_directory: str,
        collection_name: str = "diary",
    ):
        """Initialize ChromaDB persistent client.

        Args:
            persist_directory: Directory for ChromaDB persistence
            collection_name: ChromaDB collection name
        """
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"DiaryVectorStore initialized at {persist_directory} "
            f"(collection={collection_name}, count={self._collection.count()})"
        )

    async def add(
        self,
        entry_id: str,
        embedding: list[float],
        body: str,
        metadata: dict[str, Any],
    ) -> None:
        """Add or update a diary entry in ChromaDB.

        Args:
            entry_id: Unique entry identifier
            embedding: Embedding vector
            body: Entry text body
            metadata: Entry metadata dict
        """
        # ChromaDB requires float metadata values to be wrapped; int/float/str pass through
        self._collection.upsert(
            ids=[entry_id],
            embeddings=[embedding],
            documents=[body],
            metadatas=[metadata],
        )

    async def delete(self, entry_ids: list[str]) -> None:
        """Delete diary entries by ID.

        Args:
            entry_ids: List of entry IDs to delete
        """
        if entry_ids:
            self._collection.delete(ids=entry_ids)

    async def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query by embedding similarity.

        Args:
            query_embedding: Query vector
            n_results: Maximum number of results
            where: Optional ChromaDB where clause

        Returns:
            List of {id, document, metadata, distance} dicts
        """
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["embeddings", "documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        result = self._collection.query(**kwargs)

        if not result["ids"] or not result["ids"][0]:
            return []

        entries = []
        for i in range(len(result["ids"][0])):
            entry = {
                "id": result["ids"][0][i],
                "document": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
                # ChromaDB query returns embeddings as list[numpy.ndarray];
                # convert to plain list for downstream code
                "embedding": result["embeddings"][0][i].tolist()
                    if hasattr(result["embeddings"][0][i], "tolist")
                    else result["embeddings"][0][i],
            }
            entries.append(entry)
        return entries

    async def get_all_ids(self) -> list[str]:
        """Return all entry IDs in the store."""
        result = self._collection.get(include=[])
        return result["ids"] if result["ids"] else []

    async def count(self) -> int:
        """Return total number of entries."""
        return self._collection.count()

    async def get(
        self,
        entry_ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve entries by ID or where clause.

        Args:
            entry_ids: Specific IDs to retrieve
            where: ChromaDB where clause filter

        Returns:
            List of entry dicts
        """
        kwargs: dict[str, Any] = {
            "include": ["embeddings", "documents", "metadatas"],
        }
        if entry_ids:
            kwargs["ids"] = entry_ids
        if where:
            kwargs["where"] = where

        result = self._collection.get(**kwargs)

        if not result["ids"]:
            return []

        # ChromaDB returns embeddings as a numpy array (ragged/object dtype);
        # documents/metadatas are plain lists. Never truth-test an ndarray.
        embeddings = result["embeddings"]
        has_embeddings = embeddings is not None and len(embeddings) > 0

        documents = result["documents"]
        metadatas = result["metadatas"]

        entries = []
        for i in range(len(result["ids"])):
            entry: dict[str, Any] = {
                "id": result["ids"][i],
                "document": documents[i] if documents is not None and len(documents) > i else "",
                "metadata": metadatas[i] if metadatas is not None and len(metadatas) > i else {},
            }
            if has_embeddings:
                entry["embedding"] = embeddings[i].tolist()
            entries.append(entry)
        return entries
