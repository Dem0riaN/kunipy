"""PostgreSQL database initialization and schema (ТЗ-002 PostgreSQL migration)."""

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)


class PostgreSQLDatabase:
    """PostgreSQL database for memory system.

    Replaces SQLite for better scalability with large memory datasets.
    """

    def __init__(self, connection_string: str):
        """Initialize database connection.

        Args:
            connection_string: PostgreSQL connection string
                Example: "postgresql://user:password@localhost:5432/kunipy"
        """
        self.connection_string = connection_string
        self._conn: psycopg.AsyncConnection | None = None

    async def connect(self) -> psycopg.AsyncConnection:
        """Get database connection (lazy initialization)."""
        if self._conn is None or self._conn.closed:
            self._conn = await psycopg.AsyncConnection.connect(
                self.connection_string,
                row_factory=dict_row,
                autocommit=True
            )
            logger.info(f"Connected to PostgreSQL memory database")
        return self._conn

    async def close(self) -> None:
        """Close database connection."""
        if self._conn and not self._conn.closed:
            await self._conn.close()
            self._conn = None
            logger.info("Closed PostgreSQL database connection")

    async def initialize_schema(self) -> None:
        """Create database schema if not exists."""
        conn = await self.connect()

        async with conn.cursor() as cursor:
            # Table: users
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    first_seen_at TIMESTAMPTZ NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at)"
            )

            # Table: chats
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    chat_type TEXT NOT NULL,
                    title TEXT,
                    first_seen_at TIMESTAMPTZ NOT NULL,
                    last_seen_at TIMESTAMPTZ NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chats_last_seen ON chats(last_seen_at)"
            )

            # Table: conversations
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    message_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    reply_to_message_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_chat
                ON conversations(user_id, chat_id, timestamp DESC)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_chat
                ON conversations(chat_id, timestamp DESC)
            """)

            # Table: memories
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL,
                    scope TEXT NOT NULL,
                    user_id TEXT,
                    chat_id TEXT,
                    channel TEXT,
                    source_message_ids TEXT[],
                    source_type TEXT,
                    retrieval_cues TEXT[],
                    entities TEXT[],
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_used TIMESTAMPTZ,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_chat ON memories(chat_id)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)"
            )
            await cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)"
            )

            # Table: memory_embeddings (using PostgreSQL array for embeddings)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    embedding REAL[] NOT NULL,
                    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                )
            """)

            # Table: working_memory
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS working_memory (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    current_topic TEXT,
                    conversation_summary TEXT,
                    last_interaction_at TIMESTAMPTZ,
                    emotion_state TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id, chat_id, channel)
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_working_memory_user_chat
                ON working_memory(user_id, chat_id, channel)
            """)

            # Table: working_memory_items
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS working_memory_items (
                    id TEXT PRIMARY KEY,
                    working_memory_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    due_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    metadata JSONB DEFAULT '{}',
                    FOREIGN KEY (working_memory_id) REFERENCES working_memory(id) ON DELETE CASCADE
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_working_memory_items_wm
                ON working_memory_items(working_memory_id, status, priority DESC)
            """)

            # Table: memory_links
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_links (
                    from_memory_id TEXT NOT NULL,
                    to_memory_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (from_memory_id, to_memory_id),
                    FOREIGN KEY (from_memory_id) REFERENCES memories(id) ON DELETE CASCADE,
                    FOREIGN KEY (to_memory_id) REFERENCES memories(id) ON DELETE CASCADE
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_links_from
                ON memory_links(from_memory_id)
            """)

            # Table: memory_tags
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_tags (
                    memory_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (memory_id, tag),
                    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_tags_tag
                ON memory_tags(tag)
            """)

            # Table: user_preferences
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, key),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_preferences_user
                ON user_preferences(user_id)
            """)

        logger.info("PostgreSQL schema initialized successfully")
