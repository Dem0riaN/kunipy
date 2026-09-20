"""User preference repository (ТЗ-002 §7.3)."""

import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class UserPreferenceRepository:
    """Repository for per-user preference key-value pairs (ТЗ-002 §7.3).

    Stores inferred or explicit preferences like:
    - preferred_language, communication_style, topics_of_interest
    - Each has a confidence score and source (inferred/stated/observed)
    """

    def __init__(self, db_connection: sqlite3.Connection):
        self.conn = db_connection

    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        source: str = "inferred",
    ) -> None:
        """Set or update a user preference (upsert).

        Args:
            user_id: User ID
            key: Preference key
            value: Preference value
            confidence: Confidence level (0.0 to 1.0)
            source: How the preference was determined
        """
        now = datetime.now(UTC).isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_preferences (
                user_id, preference_key, preference_value,
                confidence, source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, preference_key)
            DO UPDATE SET
                preference_value = excluded.preference_value,
                confidence = excluded.confidence,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (user_id, key, value, confidence, source, now, now),
        )
        self.conn.commit()

    async def get_preference(self, user_id: str, key: str) -> dict | None:
        """Get a single preference for a user.

        Args:
            user_id: User ID
            key: Preference key

        Returns:
            Preference dict or None
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM user_preferences WHERE user_id = ? AND preference_key = ?",
            (user_id, key),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    async def get_all_preferences(self, user_id: str) -> list[dict]:
        """Get all preferences for a user.

        Args:
            user_id: User ID

        Returns:
            List of preference dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM user_preferences WHERE user_id = ? ORDER BY confidence DESC",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def delete_preference(self, user_id: str, key: str) -> bool:
        """Delete a preference.

        Args:
            user_id: User ID
            key: Preference key

        Returns:
            True if deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM user_preferences WHERE user_id = ? AND preference_key = ?",
            (user_id, key),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    async def delete_all_preferences(self, user_id: str) -> int:
        """Delete all preferences for a user.

        Args:
            user_id: User ID

        Returns:
            Number of preferences deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM user_preferences WHERE user_id = ?",
            (user_id,),
        )
        self.conn.commit()
        return cursor.rowcount
