"""SQLite database initialization and schema (ТЗ-002 Этап 3)."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryDatabase:
    """SQLite database for memory system."""

    def __init__(self, db_path: str | Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None  # autocommit mode
            )
            self._conn.row_factory = sqlite3.Row
            logger.info(f"Connected to memory database: {self.db_path}")
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Closed memory database connection")

    def initialize_schema(self) -> None:
        """Create database schema if not exists."""
        conn = self.connect()
        cursor = conn.cursor()

        # Table: users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at)")

        # Table: chats
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                chat_type TEXT NOT NULL,
                title TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_last_seen ON chats(last_seen_at)")

        # Table: conversations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                message_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reply_to_message_id TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_user_chat
            ON conversations(user_id, chat_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_chat
            ON conversations(chat_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_timestamp
            ON conversations(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_channel
            ON conversations(channel)
        """)

        # Table: memory_pieces
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_pieces (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                importance REAL NOT NULL,
                scope TEXT NOT NULL,
                user_id TEXT,
                chat_id TEXT,
                channel TEXT,
                source_type TEXT NOT NULL,
                source_message_ids TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used_at TEXT,
                usage_count INTEGER NOT NULL DEFAULT 0,
                retrieval_cues TEXT,
                entities TEXT,
                metadata TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_pieces(scope)")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_pieces(user_id, scope)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_chat ON memory_pieces(chat_id, scope)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_confidence ON memory_pieces(confidence)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_pieces(importance)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_last_used ON memory_pieces(last_used_at)
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_pieces(kind)")

        # Table: memory_embeddings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                embedding_model TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memory_pieces(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_model
            ON memory_embeddings(embedding_model)
        """)

        # Table: working_memory
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS working_memory (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                current_topic TEXT,
                conversation_summary TEXT,
                emotion_state TEXT,
                last_interaction_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
                UNIQUE(user_id, chat_id, channel)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_working_memory_context
            ON working_memory(user_id, chat_id, channel)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_working_memory_last_interaction
            ON working_memory(last_interaction_at)
        """)

        # Table: working_memory_items
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS working_memory_items (
                id TEXT PRIMARY KEY,
                working_memory_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                due_at TEXT,
                completed_at TEXT,
                metadata TEXT,
                FOREIGN KEY (working_memory_id) REFERENCES working_memory(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_wm_items_working_memory
            ON working_memory_items(working_memory_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_wm_items_type_status
            ON working_memory_items(item_type, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_wm_items_due
            ON working_memory_items(due_at)
        """)

        conn.commit()
        logger.info("Memory database schema initialized")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
