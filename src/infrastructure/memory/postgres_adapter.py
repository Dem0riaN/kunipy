"""Database connection adapter for PostgreSQL (ТЗ-002 PostgreSQL migration).

Provides unified interface for repositories to work with PostgreSQL async connection.
"""

import json
import logging
from datetime import datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


class PostgreSQLAdapter:
    """Adapter to make PostgreSQL connection work like SQLite's synchronous API.

    This adapter wraps psycopg AsyncConnection to provide a similar interface
    to sqlite3.Connection, making repository code work with minimal changes.
    """

    def __init__(self, conn: psycopg.AsyncConnection):
        """Initialize adapter.

        Args:
            conn: PostgreSQL async connection
        """
        self._conn = conn

    def cursor(self):
        """Return cursor-like object for executing queries."""
        return PostgreSQLCursor(self._conn)

    def commit(self):
        """No-op for PostgreSQL with autocommit enabled."""
        pass

    def close(self):
        """Close connection (async operation wrapped)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context
                pass
            else:
                asyncio.run(self._conn.close())
        except RuntimeError:
            pass


class PostgreSQLCursor:
    """Cursor-like wrapper for PostgreSQL async cursor."""

    def __init__(self, conn: psycopg.AsyncConnection):
        """Initialize cursor wrapper.

        Args:
            conn: PostgreSQL async connection
        """
        self._conn = conn
        self._results = []
        self.rowcount = 0

    def execute(self, query: str, params: tuple | None = None):
        """Execute query synchronously (blocks until complete).

        Args:
            query: SQL query with PostgreSQL-style placeholders ($1, $2, ...)
            params: Query parameters
        """
        import asyncio

        # Convert SQLite ? placeholders to PostgreSQL $1, $2, ...
        converted_query = query
        if params and '?' in query:
            for i in range(len(params)):
                converted_query = converted_query.replace('?', f'${i+1}', 1)

        async def _execute():
            async with self._conn.cursor() as cur:
                await cur.execute(converted_query, params)
                self.rowcount = cur.rowcount

                # Fetch results if this is a SELECT
                if cur.description:
                    self._results = await cur.fetchall()
                else:
                    self._results = []

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create new task in running loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _execute())
                    future.result()
            else:
                asyncio.run(_execute())
        except RuntimeError:
            asyncio.run(_execute())

    def fetchone(self) -> dict | None:
        """Fetch one result row.

        Returns:
            Row as dict or None
        """
        if self._results:
            return dict(self._results.pop(0))
        return None

    def fetchall(self) -> list[dict]:
        """Fetch all result rows.

        Returns:
            List of rows as dicts
        """
        results = [dict(row) for row in self._results]
        self._results = []
        return results


def serialize_for_postgres(value: Any) -> Any:
    """Serialize Python objects for PostgreSQL storage.

    Args:
        value: Value to serialize

    Returns:
        PostgreSQL-compatible value
    """
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return value  # PostgreSQL supports arrays natively
    return value


def deserialize_from_postgres(row: dict) -> dict:
    """Deserialize PostgreSQL row to Python objects.

    Args:
        row: Row dict from PostgreSQL

    Returns:
        Deserialized dict
    """
    result = {}
    for key, value in row.items():
        if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        else:
            result[key] = value
    return result
