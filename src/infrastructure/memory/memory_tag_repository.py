"""Memory tag repository (ТЗ-002 §9)."""

import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class MemoryTagRepository:
    """Repository for memory tags (ТЗ-002 §9).

    Tags are free-form strings attached to memory pieces for
    fast lookup by topic, category, or label.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        self.conn = db_connection

    async def add_tag(self, memory_id: str, tag: str) -> int:
        """Add a tag to a memory (idempotent via UNIQUE constraint).

        Args:
            memory_id: Memory ID
            tag: Tag string

        Returns:
            Tag row ID
        """
        now = datetime.now(UTC).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO memory_tags (memory_id, tag, created_at)
            VALUES (?, ?, ?)
            """,
            (memory_id, tag, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    async def get_tags_for_memory(self, memory_id: str) -> list[str]:
        """Get all tags for a memory.

        Args:
            memory_id: Memory ID

        Returns:
            List of tag strings
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag",
            (memory_id,),
        )
        return [row["tag"] for row in cursor.fetchall()]

    async def get_memories_by_tag(self, tag: str, limit: int = 100) -> list[str]:
        """Get memory IDs that have a specific tag.

        Args:
            tag: Tag string
            limit: Maximum results

        Returns:
            List of memory IDs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT memory_id FROM memory_tags WHERE tag = ? LIMIT ?",
            (tag, limit),
        )
        return [row["memory_id"] for row in cursor.fetchall()]

    async def remove_tag(self, memory_id: str, tag: str) -> bool:
        """Remove a tag from a memory.

        Args:
            memory_id: Memory ID
            tag: Tag string

        Returns:
            True if removed
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM memory_tags WHERE memory_id = ? AND tag = ?",
            (memory_id, tag),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    async def remove_all_tags(self, memory_id: str) -> int:
        """Remove all tags from a memory.

        Args:
            memory_id: Memory ID

        Returns:
            Number of tags removed
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM memory_tags WHERE memory_id = ?",
            (memory_id,),
        )
        self.conn.commit()
        return cursor.rowcount

    async def list_all_tags(self, limit: int = 200) -> list[dict]:
        """List all unique tags with usage count.

        Args:
            limit: Maximum results

        Returns:
            List of {tag, count} dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT tag, COUNT(*) as count
            FROM memory_tags
            GROUP BY tag
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
