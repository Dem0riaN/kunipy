"""Memory link repository for entity relationships (ТЗ-002 §35)."""

import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class MemoryLinkRepository:
    """Repository for memory-to-memory links (ТЗ-002 §35).

    Stores directed relationships between memory pieces:
    - "related_to": general association
    - "causes": causal link
    - "contradicts": conflicting information
    - "supports": corroborating evidence
    - "derived_from": consolidation/merge provenance
    """

    def __init__(self, db_connection: sqlite3.Connection):
        self.conn = db_connection

    async def create_link(
        self,
        from_memory_id: str,
        to_memory_id: str,
        link_type: str,
        strength: float = 1.0,
        scope: str = "global",
        provenance: str | None = None,
    ) -> int:
        """Create a link between two memories.

        Args:
            from_memory_id: Source memory ID
            to_memory_id: Target memory ID
            link_type: Type of relationship
            strength: Link strength (0.0 to 1.0)
            scope: Visibility scope
            provenance: How this link was discovered

        Returns:
            Link ID
        """
        now = datetime.now(UTC).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_links (
                from_memory_id, to_memory_id, link_type, strength,
                scope, provenance, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (from_memory_id, to_memory_id, link_type, strength, scope, provenance, now, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    async def get_links_from(self, memory_id: str) -> list[dict]:
        """Get all links originating from a memory.

        Args:
            memory_id: Source memory ID

        Returns:
            List of link dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_links WHERE from_memory_id = ?",
            (memory_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def get_links_to(self, memory_id: str) -> list[dict]:
        """Get all links targeting a memory.

        Args:
            memory_id: Target memory ID

        Returns:
            List of link dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_links WHERE to_memory_id = ?",
            (memory_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def get_all_links(self, memory_id: str) -> list[dict]:
        """Get all links involving a memory (in or out).

        Args:
            memory_id: Memory ID

        Returns:
            List of link dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory_links WHERE from_memory_id = ? OR to_memory_id = ?",
            (memory_id, memory_id),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def delete_link(self, link_id: int) -> bool:
        """Delete a link by ID.

        Args:
            link_id: Link ID

        Returns:
            True if deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM memory_links WHERE id = ?", (link_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    async def delete_links_for_memory(self, memory_id: str) -> int:
        """Delete all links involving a memory.

        Args:
            memory_id: Memory ID

        Returns:
            Number of links deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM memory_links WHERE from_memory_id = ? OR to_memory_id = ?",
            (memory_id, memory_id),
        )
        self.conn.commit()
        return cursor.rowcount
