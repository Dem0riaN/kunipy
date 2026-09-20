"""Memory repository for long-term memory storage (ТЗ-002)."""

import json
import logging
import sqlite3
from datetime import UTC, datetime

import numpy as np

from ...interfaces.memory import MemoryKind, MemoryPiece, MemoryScope

logger = logging.getLogger(__name__)


class MemoryRepository:
    """Repository for long-term memory pieces (ТЗ-002 punkt 9).

    Handles CRUD operations and metadata storage.
    Vector similarity search is delegated to ChromaDB via MemoryStore.
    """

    def __init__(self, db_connection: sqlite3.Connection, embedding_model: str = "default"):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
            embedding_model: Name of the embedding model used for vectors
        """
        self.conn = db_connection
        self._embedding_model = embedding_model

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Create new memory piece.

        Args:
            piece: Memory piece to store

        Returns:
            Memory ID
        """
        cursor = self.conn.cursor()

        # Store memory piece metadata
        cursor.execute(
            """
            INSERT INTO memory_pieces (
                id, kind, content, confidence, importance, scope,
                user_id, chat_id, channel, source_type, source_message_ids,
                created_at, updated_at, last_used_at, usage_count,
                retrieval_cues, entities, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                piece.id,
                piece.kind.value,
                piece.content,
                piece.confidence,
                piece.importance,
                piece.scope.value,
                piece.user_id,
                piece.chat_id,
                piece.channel,
                piece.source_type,
                json.dumps(piece.source_message_ids),
                piece.created_at.isoformat(),
                piece.updated_at.isoformat(),
                piece.last_used.isoformat() if piece.last_used else None,
                piece.usage_count,
                json.dumps(piece.retrieval_cues),
                json.dumps(piece.entities),
                json.dumps(piece.metadata),
            ),
        )

        # Store embedding separately (with required embedding_model and dimension columns)
        if piece.embedding is not None and len(piece.embedding) > 0:
            embedding_array = np.array(piece.embedding, dtype=np.float32)
            cursor.execute(
                """
                INSERT INTO memory_embeddings (
                    memory_id, embedding, embedding_model, dimension, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    piece.id,
                    embedding_array.tobytes(),
                    self._embedding_model,
                    len(piece.embedding),
                    datetime.now(UTC).isoformat(),
                ),
            )

        self.conn.commit()
        logger.debug(f"Created memory {piece.id} with scope {piece.scope.value}")
        return piece.id

    async def get_memory(self, memory_id: str) -> MemoryPiece | None:
        """Get memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory piece if found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_pieces WHERE id = ?",
            (memory_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        # Get embedding
        cursor.execute(
            "SELECT embedding FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        )
        emb_row = cursor.fetchone()
        embedding = None
        if emb_row:
            embedding_bytes = emb_row["embedding"]
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()

        return self._row_to_memory_piece(row, embedding)

    async def update_memory(self, piece: MemoryPiece) -> bool:
        """Update existing memory piece.

        Args:
            piece: Memory piece with updated fields

        Returns:
            True if updated
        """
        piece.updated_at = datetime.now(UTC)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE memory_pieces
            SET content = ?, confidence = ?, importance = ?, scope = ?,
                updated_at = ?, last_used_at = ?, usage_count = ?,
                retrieval_cues = ?, entities = ?, metadata = ?
            WHERE id = ?
            """,
            (
                piece.content,
                piece.confidence,
                piece.importance,
                piece.scope.value,
                piece.updated_at.isoformat(),
                piece.last_used.isoformat() if piece.last_used else None,
                piece.usage_count,
                json.dumps(piece.retrieval_cues),
                json.dumps(piece.entities),
                json.dumps(piece.metadata),
                piece.id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory piece.

        Args:
            memory_id: Memory ID

        Returns:
            True if deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM memory_pieces WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    async def get_by_scope(
        self,
        scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryPiece]:
        """Get memories by scope without embedding search.

        Args:
            scope: Memory scope
            user_id: Filter by user
            chat_id: Filter by chat
            limit: Maximum results

        Returns:
            List of memory pieces
        """
        cursor = self.conn.cursor()

        sql = "SELECT * FROM memory_pieces WHERE scope = ?"
        params = [scope.value]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        if chat_id:
            sql += " AND chat_id = ?"
            params.append(chat_id)

        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # Get embeddings for each
        memories = []
        for row in rows:
            cursor.execute(
                "SELECT embedding FROM memory_embeddings WHERE memory_id = ?",
                (row["id"],),
            )
            emb_row = cursor.fetchone()
            embedding = None
            if emb_row:
                embedding_bytes = emb_row["embedding"]
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()

            memories.append(self._row_to_memory_piece(row, embedding))

        return memories

    def _row_to_memory_piece(
        self, row: sqlite3.Row, embedding: list[float] | None
    ) -> MemoryPiece:
        """Convert database row to MemoryPiece.

        Args:
            row: Database row
            embedding: Embedding vector (fetched separately)

        Returns:
            MemoryPiece instance
        """
        return MemoryPiece(
            id=row["id"],
            kind=MemoryKind(row["kind"]),
            content=row["content"],
            confidence=row["confidence"],
            importance=row["importance"],
            scope=MemoryScope(row["scope"]),
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            channel=row["channel"],
            source_type=row["source_type"],
            source_message_ids=json.loads(row["source_message_ids"]) if row["source_message_ids"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_used=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else datetime.now(UTC),
            usage_count=row["usage_count"],
            embedding=embedding or [],
            retrieval_cues=json.loads(row["retrieval_cues"]) if row["retrieval_cues"] else [],
            entities=json.loads(row["entities"]) if row["entities"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
