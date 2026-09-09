"""Message delivery storage implementation (ТЗ-001 punkt 12-18)."""

import sqlite3
import hashlib
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from src.domain.delivery.models import MessageDeliveryRecord
from src.interfaces.delivery import DeliveryState


class MessageDeliveryStorage:
    """Persistent storage for delivery records.

    Uses SQLite for durability across restarts.
    Implements ТЗ-001 punkt 12 storage requirements.
    """

    def __init__(self, db_path: Path):
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file
        """
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    async def initialize(self) -> None:
        """Initialize database schema."""
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None  # Autocommit mode
        )

        # Enable WAL mode for better concurrency
        self._conn.execute("PRAGMA journal_mode=WAL")

        # Create table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_records (
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                state TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                delivered_at TEXT,
                failed_at TEXT,
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                text_hash TEXT,
                worker_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                PRIMARY KEY (chat_id, message_id)
            )
        """)

        # Index for pending verifications
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_sent_at
            ON delivery_records(state, sent_at)
        """)

        # Index for duplicate detection
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_hash_sent
            ON delivery_records(chat_id, text_hash, sent_at)
        """)

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def save_record(self, record: MessageDeliveryRecord) -> None:
        """Save or update delivery record.

        Args:
            record: Record to save
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        now = datetime.now().isoformat()

        self._conn.execute("""
            INSERT INTO delivery_records (
                message_id, chat_id, state, sent_at,
                delivered_at, failed_at, retry_count,
                error_message, text_hash, worker_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                state = excluded.state,
                delivered_at = excluded.delivered_at,
                failed_at = excluded.failed_at,
                retry_count = excluded.retry_count,
                error_message = excluded.error_message,
                updated_at = excluded.updated_at
        """, (
            record.message_id,
            record.chat_id,
            record.state.value,
            record.sent_at.isoformat(),
            record.delivered_at.isoformat() if record.delivered_at else None,
            record.failed_at.isoformat() if record.failed_at else None,
            record.retry_count,
            record.error_message,
            record.text_hash,
            record.worker_id,
            now,
            now
        ))

    async def get_record(
        self,
        chat_id: int,
        message_id: int
    ) -> Optional[MessageDeliveryRecord]:
        """Retrieve delivery record.

        Args:
            chat_id: Chat ID
            message_id: Message ID

        Returns:
            Record if found, None otherwise
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        cursor = self._conn.execute("""
            SELECT message_id, chat_id, state, sent_at,
                   delivered_at, failed_at, retry_count,
                   error_message, text_hash, worker_id
            FROM delivery_records
            WHERE chat_id = ? AND message_id = ?
        """, (chat_id, message_id))

        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_record(row)

    async def get_pending_verifications(self) -> List[MessageDeliveryRecord]:
        """Get all messages pending verification.

        Returns:
            List of records in SENT state
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        cursor = self._conn.execute("""
            SELECT message_id, chat_id, state, sent_at,
                   delivered_at, failed_at, retry_count,
                   error_message, text_hash, worker_id
            FROM delivery_records
            WHERE state = ?
            ORDER BY sent_at ASC
        """, (DeliveryState.SENT.value,))

        return [self._row_to_record(row) for row in cursor.fetchall()]

    async def find_recent_by_hash(
        self,
        chat_id: int,
        text_hash: str,
        window_seconds: float
    ) -> List[MessageDeliveryRecord]:
        """Find recent messages with same hash.

        Args:
            chat_id: Chat ID
            text_hash: Message content hash
            window_seconds: Time window to search

        Returns:
            List of matching records
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        cutoff = datetime.now().timestamp() - window_seconds
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

        cursor = self._conn.execute("""
            SELECT message_id, chat_id, state, sent_at,
                   delivered_at, failed_at, retry_count,
                   error_message, text_hash, worker_id
            FROM delivery_records
            WHERE chat_id = ?
              AND text_hash = ?
              AND sent_at >= ?
              AND state IN (?, ?, ?)
            ORDER BY sent_at DESC
        """, (
            chat_id,
            text_hash,
            cutoff_iso,
            DeliveryState.SENT.value,
            DeliveryState.DELIVERED.value,
            DeliveryState.RETRY_PENDING.value
        ))

        return [self._row_to_record(row) for row in cursor.fetchall()]

    async def count_records(self) -> int:
        """Count total records in storage.

        Returns:
            Total record count
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        cursor = self._conn.execute("SELECT COUNT(*) FROM delivery_records")
        return cursor.fetchone()[0]

    async def cleanup_old_records(self, days: int = 7) -> int:
        """Remove old delivered/failed records.

        Args:
            days: Keep records newer than this many days

        Returns:
            Number of records deleted
        """
        if not self._conn:
            raise RuntimeError("Storage not initialized")

        cutoff = datetime.now().timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

        cursor = self._conn.execute("""
            DELETE FROM delivery_records
            WHERE state IN (?, ?)
              AND updated_at < ?
        """, (
            DeliveryState.DELIVERED.value,
            DeliveryState.FAILED.value,
            cutoff_iso
        ))

        return cursor.rowcount

    def _row_to_record(self, row: tuple) -> MessageDeliveryRecord:
        """Convert database row to record.

        Args:
            row: SQLite row tuple

        Returns:
            MessageDeliveryRecord instance
        """
        return MessageDeliveryRecord(
            message_id=row[0],
            chat_id=row[1],
            state=DeliveryState(row[2]),
            sent_at=datetime.fromisoformat(row[3]),
            delivered_at=datetime.fromisoformat(row[4]) if row[4] else None,
            failed_at=datetime.fromisoformat(row[5]) if row[5] else None,
            retry_count=row[6],
            error_message=row[7],
            text_hash=row[8],
            worker_id=row[9]
        )

    @staticmethod
    def compute_text_hash(text: str) -> str:
        """Compute hash for duplicate detection.

        Args:
            text: Message text

        Returns:
            SHA-256 hash hex string
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
