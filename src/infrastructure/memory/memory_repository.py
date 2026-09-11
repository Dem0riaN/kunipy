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

    Handles CRUD operations and vector similarity search.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

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

        # Store embedding separately
        if piece.embedding:
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
                    "text-embedding-3-small",  # TODO: get from config
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
            "SELECT embedding, dimension FROM memory_embeddings WHERE memory_id = ?",
            (memory_id,),
        )
        emb_row = cursor.fetchone()
        embedding = None
        if emb_row:
            embedding_bytes = emb_row["embedding"]
            dimension = emb_row["dimension"]
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

    async def search_by_embedding(
        self,
        query_embedding: list[float],
        scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 10,
        min_confidence: float = -1.0,
    ) -> list[tuple[MemoryPiece, float]]:
        """Search memory by embedding similarity.

        Args:
            query_embedding: Query vector
            scope: Memory scope filter
            user_id: Filter by user
            chat_id: Filter by chat
            limit: Maximum results
            min_confidence: Minimum confidence threshold

        Returns:
            List of (memory_piece, similarity_score) tuples, sorted by score
        """
        cursor = self.conn.cursor()

        # Build query with filters
        sql = """
            SELECT m.*, e.embedding, e.dimension
            FROM memory_pieces m
            JOIN memory_embeddings e ON m.id = e.memory_id
            WHERE m.scope = ? AND m.confidence >= ?
        """
        params = [scope.value, min_confidence]

        if user_id:
            sql += " AND m.user_id = ?"
            params.append(user_id)

        if chat_id:
            sql += " AND m.chat_id = ?"
            params.append(chat_id)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # Calculate similarity scores
        query_vec = np.array(query_embedding, dtype=np.float32)
        results = []

        for row in rows:
            embedding_bytes = row["embedding"]
            dimension = row["dimension"]
            memory_vec = np.frombuffer(embedding_bytes, dtype=np.float32)

            # Cosine similarity
            similarity = self._cosine_similarity(query_vec, memory_vec)

            # Normalize to 0-1 range
            normalized_score = (similarity + 1.0) / 2.0

            # Add confidence boost
            final_score = normalized_score + row["confidence"] * 0.1

            embedding_list = memory_vec.tolist()
            memory_piece = self._row_to_memory_piece(row, embedding_list)
            results.append((memory_piece, final_score))

        # Sort by score and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

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
                "SELECT embedding, dimension FROM memory_embeddings WHERE memory_id = ?",
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

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity (-1 to 1)
        """
        if a.size != b.size:
            raise ValueError(f"Vector size mismatch: {a.size} vs {b.size}")
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
