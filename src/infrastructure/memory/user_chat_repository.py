"""User and Chat repositories (ТЗ-002)."""

import json
import logging
import sqlite3
from datetime import UTC, datetime

from ...domain.memory_models import Chat, User

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user entities (ТЗ-002 punkt 4)."""

    def __init__(self, db_connection: sqlite3.Connection):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

    async def create_user(self, user: User) -> None:
        """Create new user.

        Args:
            user: User entity
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (
                user_id, display_name, first_seen_at, last_seen_at,
                metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.user_id,
                user.display_name,
                user.first_seen_at.isoformat(),
                user.last_seen_at.isoformat(),
                json.dumps(user.metadata),
                user.created_at.isoformat(),
                user.updated_at.isoformat(),
            ),
        )
        self.conn.commit()
        logger.debug(f"Created user {user.user_id}")

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User if found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def update_user(self, user: User) -> bool:
        """Update existing user.

        Args:
            user: User entity with updated fields

        Returns:
            True if updated
        """
        user.updated_at = datetime.now(UTC)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET display_name = ?, last_seen_at = ?, metadata = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                user.display_name,
                user.last_seen_at.isoformat(),
                json.dumps(user.metadata),
                user.updated_at.isoformat(),
                user.user_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    async def get_or_create_user(
        self, user_id: str, display_name: str
    ) -> User:
        """Get existing user or create new one.

        Args:
            user_id: User ID
            display_name: User display name

        Returns:
            User entity
        """
        user = await self.get_user(user_id)
        if user:
            # Update last_seen_at
            user.last_seen_at = datetime.now(UTC)
            await self.update_user(user)
            return user

        # Create new user
        now = datetime.now(UTC)
        user = User(
            user_id=user_id,
            display_name=display_name,
            first_seen_at=now,
            last_seen_at=now,
        )
        await self.create_user(user)
        return user

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Convert database row to User.

        Args:
            row: Database row

        Returns:
            User instance
        """
        return User(
            user_id=row["user_id"],
            display_name=row["display_name"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class ChatRepository:
    """Repository for chat entities (ТЗ-002 punkt 4)."""

    def __init__(self, db_connection: sqlite3.Connection):
        """Initialize repository.

        Args:
            db_connection: SQLite database connection
        """
        self.conn = db_connection

    async def create_chat(self, chat: Chat) -> None:
        """Create new chat.

        Args:
            chat: Chat entity
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO chats (
                chat_id, chat_type, title, first_seen_at, last_seen_at,
                metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat.chat_id,
                chat.chat_type,
                chat.title,
                chat.first_seen_at.isoformat(),
                chat.last_seen_at.isoformat(),
                json.dumps(chat.metadata),
                chat.created_at.isoformat(),
                chat.updated_at.isoformat(),
            ),
        )
        self.conn.commit()
        logger.debug(f"Created chat {chat.chat_id}")

    async def get_chat(self, chat_id: str) -> Chat | None:
        """Get chat by ID.

        Args:
            chat_id: Chat ID

        Returns:
            Chat if found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return self._row_to_chat(row) if row else None

    async def update_chat(self, chat: Chat) -> bool:
        """Update existing chat.

        Args:
            chat: Chat entity with updated fields

        Returns:
            True if updated
        """
        chat.updated_at = datetime.now(UTC)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE chats
            SET title = ?, last_seen_at = ?, metadata = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (
                chat.title,
                chat.last_seen_at.isoformat(),
                json.dumps(chat.metadata),
                chat.updated_at.isoformat(),
                chat.chat_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    async def get_or_create_chat(
        self, chat_id: str, chat_type: str, title: str | None = None
    ) -> Chat:
        """Get existing chat or create new one.

        Args:
            chat_id: Chat ID
            chat_type: Chat type ("private", "group", "supergroup")
            title: Chat title (optional)

        Returns:
            Chat entity
        """
        chat = await self.get_chat(chat_id)
        if chat:
            # Update last_seen_at
            chat.last_seen_at = datetime.now(UTC)
            await self.update_chat(chat)
            return chat

        # Create new chat
        now = datetime.now(UTC)
        chat = Chat(
            chat_id=chat_id,
            chat_type=chat_type,
            title=title,
            first_seen_at=now,
            last_seen_at=now,
        )
        await self.create_chat(chat)
        return chat

    def _row_to_chat(self, row: sqlite3.Row) -> Chat:
        """Convert database row to Chat.

        Args:
            row: Database row

        Returns:
            Chat instance
        """
        return Chat(
            chat_id=row["chat_id"],
            chat_type=row["chat_type"],
            title=row["title"],
            first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
