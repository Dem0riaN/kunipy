"""Async PostgreSQL adapter for repository compatibility (ТЗ-002)."""

import json
import logging
from datetime import datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


class AsyncPostgreSQLAdapter:
    """Fully async adapter for PostgreSQL repositories.

    This version is fully async and doesn't try to wrap async calls in sync interface.
    Repositories must be updated to use async methods.
    """

    def __init__(self, conn: psycopg.AsyncConnection):
        """Initialize adapter.

        Args:
            conn: PostgreSQL async connection
        """
        self._conn = conn

    async def execute(self, query: str, params: tuple | None = None) -> list[dict]:
        """Execute query and return results.

        Args:
            query: SQL query (will convert ? to $1, $2, ...)
            params: Query parameters

        Returns:
            List of result rows as dicts
        """
        # Convert SQLite ? placeholders to PostgreSQL $1, $2, ...
        if params and '?' in query:
            pg_query = query
            for i in range(len(params)):
                pg_query = pg_query.replace('?', f'${i+1}', 1)
        else:
            pg_query = query

        async with self._conn.cursor() as cur:
            await cur.execute(pg_query, params)

            # Return results for SELECT queries
            if cur.description:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
            return []

    async def execute_one(self, query: str, params: tuple | None = None) -> dict | None:
        """Execute query and return first result.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            First row as dict or None
        """
        results = await self.execute(query, params)
        return results[0] if results else None

    async def commit(self):
        """No-op for PostgreSQL with autocommit enabled."""
        pass

    async def close(self):
        """Close connection."""
        if not self._conn.closed:
            await self._conn.close()


def convert_to_postgres_type(value: Any) -> Any:
    """Convert Python value to PostgreSQL-compatible type.

    Args:
        value: Python value

    Returns:
        PostgreSQL-compatible value
    """
    if isinstance(value, datetime):
        return value
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return value  # PostgreSQL supports arrays
    return value


def convert_from_postgres_type(value: Any) -> Any:
    """Convert PostgreSQL value to Python type.

    Args:
        value: PostgreSQL value

    Returns:
        Python value
    """
    if isinstance(value, str):
        # Try to parse JSON strings
        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
    return value
