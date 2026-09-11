"""Async-compatible PostgreSQL connection wrapper (ТЗ-002)."""

import json
import logging
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


class AsyncPostgreSQLConnection:
    """Async PostgreSQL connection wrapper that mimics sqlite3.Connection interface.

    This wrapper allows repositories to work with PostgreSQL without changing
    their async/await structure.
    """

    def __init__(self, conn: psycopg.AsyncConnection):
        """Initialize wrapper.

        Args:
            conn: PostgreSQL async connection
        """
        self._conn = conn

    def cursor(self):
        """Return cursor wrapper."""
        return AsyncPostgreSQLCursor(self._conn)

    def commit(self):
        """No-op for autocommit mode."""
        pass

    async def close(self):
        """Close connection."""
        if not self._conn.closed:
            await self._conn.close()


class AsyncPostgreSQLCursor:
    """Async PostgreSQL cursor wrapper that mimics sqlite3.Cursor interface."""

    def __init__(self, conn: psycopg.AsyncConnection):
        """Initialize cursor wrapper.

        Args:
            conn: PostgreSQL async connection
        """
        self._conn = conn
        self._last_results = []
        self.rowcount = 0

    async def execute_async(self, query: str, params: tuple | None = None):
        """Execute query asynchronously.

        Args:
            query: SQL query with ? placeholders
            params: Query parameters
        """
        # Convert SQLite ? placeholders to PostgreSQL $1, $2, ...
        converted_query = query
        if params and '?' in query:
            for i in range(len(params)):
                converted_query = converted_query.replace('?', f'${i+1}', 1)

        async with self._conn.cursor() as cur:
            await cur.execute(converted_query, params)
            self.rowcount = cur.rowcount

            # Fetch results if SELECT
            if cur.description:
                rows = await cur.fetchall()
                self._last_results = [dict(row) for row in rows]
            else:
                self._last_results = []

    def execute(self, query: str, params: tuple | None = None):
        """Synchronous execute - should not be called directly.

        This method exists for compatibility but will raise an error.
        Use execute_async instead.
        """
        raise RuntimeError(
            "Synchronous execute() not supported with async PostgreSQL. "
            "Repository code must be updated to use async/await properly."
        )

    def fetchone(self) -> dict | None:
        """Fetch one result.

        Returns:
            Row as dict or None
        """
        if self._last_results:
            return self._last_results.pop(0)
        return None

    def fetchall(self) -> list[dict]:
        """Fetch all results.

        Returns:
            List of rows as dicts
        """
        results = self._last_results
        self._last_results = []
        return results
