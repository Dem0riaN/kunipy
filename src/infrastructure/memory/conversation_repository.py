"""Conversation repository for message history storage (ТЗ-002)."""

import json
import logging
import sqlite3
from datetime import datetime

from ...domain.memory_models import ConversationMessage

logger = logging.getLogger(__name__)


class ConversationRepository:
    """Repository for conversation history (ТЗ-002 punkt 20).

    Stores raw conversation messages as primary source of truth.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

    async def store_message(self, msg: ConversationMessage) -> None:
        """Store conversation message.

        Args:
            msg: Message to store
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversations (
                message_id, user_id, chat_id, channel, timestamp, role, content,
                reply_to_message_id, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg.message_id,
                msg.user_id,
                msg.chat_id,
                msg.channel,
                msg.timestamp.isoformat(),
                msg.role,
                msg.content,
                msg.reply_to_message_id,
                json.dumps(msg.metadata),
                msg.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        logger.debug(f"Stored message {msg.message_id} in conversation history")

    async def get_conversation_history(
        self,
        user_id: str,
        chat_id: str,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        """Get conversation history.

        Args:
            user_id: User ID
            chat_id: Chat ID
            limit: Maximum messages to return
            before: Get messages before this timestamp

        Returns:
            List of messages, newest first
        """
        cursor = self.conn.cursor()

        if before:
            cursor.execute(
                """
                SELECT * FROM conversations
                WHERE user_id = ? AND chat_id = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, chat_id, before.isoformat(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM conversations
                WHERE user_id = ? AND chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, chat_id, limit),
            )

        rows = cursor.fetchall()
        messages = [self._row_to_message(row) for row in rows]
        return messages

    async def get_message(self, message_id: str) -> ConversationMessage | None:
        """Get single message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message if found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM conversations WHERE message_id = ?",
            (message_id,),
        )
        row = cursor.fetchone()
        return self._row_to_message(row) if row else None

    async def get_chat_history(
        self,
        chat_id: str,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[ConversationMessage]:
        """Get all messages in chat (multi-user).

        Args:
            chat_id: Chat ID
            limit: Maximum messages to return
            before: Get messages before this timestamp

        Returns:
            List of messages, newest first
        """
        cursor = self.conn.cursor()

        if before:
            cursor.execute(
                """
                SELECT * FROM conversations
                WHERE chat_id = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (chat_id, before.isoformat(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM conversations
                WHERE chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )

        rows = cursor.fetchall()
        messages = [self._row_to_message(row) for row in rows]
        return messages

    async def search_messages(
        self,
        query: str,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationMessage]:
        """Search messages by text content.

        Args:
            query: Search query
            user_id: Filter by user
            chat_id: Filter by chat
            limit: Maximum results

        Returns:
            List of matching messages
        """
        cursor = self.conn.cursor()

        sql = "SELECT * FROM conversations WHERE content LIKE ?"
        params = [f"%{query}%"]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        if chat_id:
            sql += " AND chat_id = ?"
            params.append(chat_id)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        messages = [self._row_to_message(row) for row in rows]
        return messages

    def _row_to_message(self, row: sqlite3.Row) -> ConversationMessage:
        """Convert database row to ConversationMessage.

        Args:
            row: Database row

        Returns:
            ConversationMessage instance
        """
        return ConversationMessage(
            message_id=row["message_id"],
            user_id=row["user_id"],
            chat_id=row["chat_id"],
            channel=row["channel"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            role=row["role"],
            content=row["content"],
            reply_to_message_id=row["reply_to_message_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )
