"""Working memory repository (ТЗ-002)."""

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime

from ...domain.memory_models import WorkingMemoryItem
from ...interfaces.memory import WorkingMemoryContext

logger = logging.getLogger(__name__)


class WorkingMemoryRepository:
    """Repository for working memory (ТЗ-002 punkt 7.6).

    Manages current interaction state, promises, plans, pending questions.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

    async def get_context(
        self, user_id: str, chat_id: str, channel: str
    ) -> WorkingMemoryContext:
        """Get working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel

        Returns:
            Working memory context (creates empty if doesn't exist)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM working_memory
            WHERE user_id = ? AND chat_id = ? AND channel = ?
            """,
            (user_id, chat_id, channel),
        )
        row = cursor.fetchone()

        if row:
            # Load existing context
            context = self._row_to_context(row)

            # Load items
            cursor.execute(
                """
                SELECT * FROM working_memory_items
                WHERE working_memory_id = ? AND status = 'active'
                ORDER BY priority DESC, created_at ASC
                """,
                (row["id"],),
            )
            item_rows = cursor.fetchall()

            # Categorize items
            for item_row in item_rows:
                item = self._row_to_item(item_row)
                if item.item_type == "promise":
                    context.promises.append({
                        "id": item.id,
                        "content": item.content,
                        "created_at": item.created_at.isoformat(),
                    })
                elif item.item_type == "plan":
                    context.plans.append({
                        "id": item.id,
                        "content": item.content,
                        "due_at": item.due_at.isoformat() if item.due_at else None,
                        "created_at": item.created_at.isoformat(),
                    })
                elif item.item_type == "question":
                    context.pending_questions.append(item.content)

            return context
        else:
            # Create empty context
            return WorkingMemoryContext(
                user_id=user_id,
                chat_id=chat_id,
                channel=channel,
                last_interaction=datetime.now(UTC),
            )

    async def update_context(
        self, user_id: str, chat_id: str, channel: str, updates: dict[str, any]
    ) -> None:
        """Update working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            updates: Fields to update
        """
        cursor = self.conn.cursor()

        # Check if context exists
        cursor.execute(
            """
            SELECT id FROM working_memory
            WHERE user_id = ? AND chat_id = ? AND channel = ?
            """,
            (user_id, chat_id, channel),
        )
        row = cursor.fetchone()

        now = datetime.now(UTC)

        if row:
            # Update existing
            wm_id = row["id"]
            set_clauses = []
            params = []

            if "current_topic" in updates:
                set_clauses.append("current_topic = ?")
                params.append(updates["current_topic"])

            if "conversation_summary" in updates:
                set_clauses.append("conversation_summary = ?")
                params.append(updates["conversation_summary"])

            if "emotion_state" in updates:
                set_clauses.append("emotion_state = ?")
                params.append(updates["emotion_state"])

            if "metadata" in updates:
                set_clauses.append("metadata = ?")
                params.append(json.dumps(updates["metadata"]))

            # Always update last_interaction and updated_at
            set_clauses.append("last_interaction_at = ?")
            set_clauses.append("updated_at = ?")
            params.extend([now.isoformat(), now.isoformat()])

            params.append(wm_id)

            sql = f"UPDATE working_memory SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(sql, tuple(params))
        else:
            # Create new (PostgreSQL will auto-generate SERIAL id)
            cursor.execute(
                """
                INSERT INTO working_memory (
                    user_id, chat_id, channel,
                    current_topic, conversation_summary, emotion_state,
                    last_interaction_at, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    chat_id,
                    channel,
                    updates.get("current_topic"),
                    updates.get("conversation_summary"),
                    updates.get("emotion_state"),
                    now.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    json.dumps(updates.get("metadata", {})),
                ),
            )

        self.conn.commit()

    async def add_item(
        self, user_id: str, chat_id: str, channel: str, item: WorkingMemoryItem
    ) -> str:
        """Add item to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            item: Working memory item

        Returns:
            Item ID
        """
        cursor = self.conn.cursor()

        # Get or create working memory context
        cursor.execute(
            """
            SELECT id FROM working_memory
            WHERE user_id = ? AND chat_id = ? AND channel = ?
            """,
            (user_id, chat_id, channel),
        )
        row = cursor.fetchone()

        if not row:
            # Create context first
            await self.update_context(user_id, chat_id, channel, {})
            cursor.execute(
                """
                SELECT id FROM working_memory
                WHERE user_id = ? AND chat_id = ? AND channel = ?
                """,
                (user_id, chat_id, channel),
            )
            row = cursor.fetchone()

        wm_id = row["id"]

        # Insert item
        cursor.execute(
            """
            INSERT INTO working_memory_items (
                id, working_memory_id, item_type, content, status, priority,
                created_at, due_at, completed_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                wm_id,
                item.item_type,
                item.content,
                item.status,
                item.priority,
                item.created_at.isoformat(),
                item.due_at.isoformat() if item.due_at else None,
                item.completed_at.isoformat() if item.completed_at else None,
                json.dumps(item.metadata),
            ),
        )
        self.conn.commit()
        logger.debug(f"Added {item.item_type} to working memory: {item.id}")
        return item.id

    async def get_items(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        item_type: str | None = None,
        status: str = "active",
    ) -> list[WorkingMemoryItem]:
        """Get working memory items.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            item_type: Filter by type (optional)
            status: Filter by status (default "active")

        Returns:
            List of items
        """
        cursor = self.conn.cursor()

        # Get working memory ID
        cursor.execute(
            """
            SELECT id FROM working_memory
            WHERE user_id = ? AND chat_id = ? AND channel = ?
            """,
            (user_id, chat_id, channel),
        )
        row = cursor.fetchone()
        if not row:
            return []

        wm_id = row["id"]

        # Query items
        sql = """
            SELECT * FROM working_memory_items
            WHERE working_memory_id = ? AND status = ?
        """
        params = [wm_id, status]

        if item_type:
            sql += " AND item_type = ?"
            params.append(item_type)

        sql += " ORDER BY priority DESC, created_at ASC"

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [self._row_to_item(row) for row in rows]

    async def update_item(self, item_id: str, updates: dict[str, any]) -> bool:
        """Update working memory item.

        Args:
            item_id: Item ID
            updates: Fields to update

        Returns:
            True if updated
        """
        cursor = self.conn.cursor()

        set_clauses = []
        params = []

        if "content" in updates:
            set_clauses.append("content = ?")
            params.append(updates["content"])

        if "status" in updates:
            set_clauses.append("status = ?")
            params.append(updates["status"])

        if "priority" in updates:
            set_clauses.append("priority = ?")
            params.append(updates["priority"])

        if "due_at" in updates:
            set_clauses.append("due_at = ?")
            val = updates["due_at"]
            params.append(val.isoformat() if val else None)

        if "completed_at" in updates:
            set_clauses.append("completed_at = ?")
            val = updates["completed_at"]
            params.append(val.isoformat() if val else None)

        if "metadata" in updates:
            set_clauses.append("metadata = ?")
            params.append(json.dumps(updates["metadata"]))

        if not set_clauses:
            return False

        params.append(item_id)
        sql = f"UPDATE working_memory_items SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(sql, params)
        self.conn.commit()
        return cursor.rowcount > 0

    async def complete_item(self, item_id: str) -> bool:
        """Mark item as completed.

        Args:
            item_id: Item ID

        Returns:
            True if updated
        """
        return await self.update_item(
            item_id,
            {"status": "completed", "completed_at": datetime.now(UTC)},
        )

    async def clear_context(
        self, user_id: str, chat_id: str, channel: str
    ) -> None:
        """Clear working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            DELETE FROM working_memory
            WHERE user_id = ? AND chat_id = ? AND channel = ?
            """,
            (user_id, chat_id, channel),
        )
        self.conn.commit()
        logger.debug(f"Cleared working memory for {user_id}/{chat_id}/{channel}")

    def _row_to_context(self, row: sqlite3.Row) -> WorkingMemoryContext:
        """Convert database row to WorkingMemoryContext.

        Args:
            row: Database row

        Returns:
            WorkingMemoryContext instance
        """
        return WorkingMemoryContext(
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            channel=row["channel"],
            current_topic=row["current_topic"],
            conversation_summary=row["conversation_summary"],
            emotion_state=row["emotion_state"],
            last_interaction=datetime.fromisoformat(row["last_interaction_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_item(self, row: sqlite3.Row) -> WorkingMemoryItem:
        """Convert database row to WorkingMemoryItem.

        Args:
            row: Database row

        Returns:
            WorkingMemoryItem instance
        """
        return WorkingMemoryItem(
            id=row["id"],
            item_type=row["item_type"],
            content=row["content"],
            status=row["status"],
            priority=row["priority"],
            created_at=datetime.fromisoformat(row["created_at"]),
            due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
