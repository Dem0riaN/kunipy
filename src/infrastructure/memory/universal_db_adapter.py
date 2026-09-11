"""Universal database adapter for both SQLite and PostgreSQL (ТЗ-002)."""

import asyncio
import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


class UniversalDBAdapter:
    """Universal adapter that works with both SQLite and PostgreSQL.

    Provides a unified synchronous-looking interface that works correctly
    whether the underlying connection is sync (SQLite) or async (PostgreSQL).
    """

    def __init__(self, connection):
        """Initialize adapter.

        Args:
            connection: Either sqlite3.Connection or psycopg.AsyncConnection
        """
        self._conn = connection
        self._is_postgres = hasattr(connection, 'cursor') and asyncio.iscoroutinefunction(
            getattr(connection, 'execute', None) if hasattr(connection, 'execute') else lambda: None
        ) or str(type(connection)).find('psycopg') != -1

    def cursor(self):
        """Get cursor."""
        return UniversalCursor(self._conn, self._is_postgres)

    def commit(self):
        """Commit transaction (no-op for PostgreSQL autocommit)."""
        if not self._is_postgres:
            self._conn.commit()

    def close(self):
        """Close connection."""
        if self._is_postgres:
            # For PostgreSQL, we need to handle async close
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't await in sync context, skip
                    pass
                else:
                    asyncio.run(self._conn.close())
            except RuntimeError:
                pass
        else:
            self._conn.close()


class UniversalCursor:
    """Universal cursor that works with both SQLite and PostgreSQL."""

    def __init__(self, connection, is_postgres: bool):
        """Initialize cursor.

        Args:
            connection: Database connection
            is_postgres: True if PostgreSQL connection
        """
        self._conn = connection
        self._is_postgres = is_postgres
        self._results = []
        self.rowcount = 0

    def execute(self, query: str, params: tuple | None = None):
        """Execute query.

        Args:
            query: SQL query
            params: Query parameters
        """
        if self._is_postgres:
            self._execute_postgres(query, params)
        else:
            self._execute_sqlite(query, params)

    def _execute_sqlite(self, query: str, params: tuple | None = None):
        """Execute query on SQLite.

        Args:
            query: SQL query
            params: Query parameters
        """
        cur = self._conn.cursor()
        cur.execute(query, params or ())
        self.rowcount = cur.rowcount

        # Store results
        if cur.description:
            self._results = [dict(row) if hasattr(row, 'keys') else
                           {desc[0]: val for desc, val in zip(cur.description, row)}
                           for row in cur.fetchall()]
        else:
            self._results = []

    def _execute_postgres(self, query: str, params: tuple | None = None):
        """Execute query on PostgreSQL.

        Args:
            query: SQL query with ? placeholders
            params: Query parameters
        """
        # Convert SQLite ? to PostgreSQL %s (psycopg3 uses %s, not $1)
        converted_query = query.replace('?', '%s')

        # Capture converted values for async context
        final_query = converted_query
        final_params = params

        # Execute in a new async context
        async def _do_execute():
            async with self._conn.cursor() as cur:
                await cur.execute(final_query, final_params)
                self.rowcount = cur.rowcount

                if cur.description:
                    rows = await cur.fetchall()
                    # Convert PostgreSQL types to match SQLite format
                    self._results = []
                    for row in rows:
                        row_dict = dict(row)
                        # Convert PostgreSQL types to SQLite-compatible format
                        converted_row = {}
                        for key, value in row_dict.items():
                            if hasattr(value, 'isoformat'):  # datetime/date objects
                                converted_row[key] = value.isoformat()
                            elif isinstance(value, dict):  # JSONB -> JSON string
                                converted_row[key] = json.dumps(value)
                            elif isinstance(value, list):  # Array -> JSON string
                                converted_row[key] = json.dumps(value)
                            else:
                                converted_row[key] = value
                        self._results.append(converted_row)
                else:
                    self._results = []

        # Run async operation
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context - need to run in executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _do_execute())
                    future.result()
            else:
                # We're in sync context
                asyncio.run(_do_execute())
        except RuntimeError as e:
            # Fallback - create new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_do_execute())
            finally:
                loop.close()

    def fetchone(self) -> dict | None:
        """Fetch one result row.

        Returns:
            Row as dict or None
        """
        if self._results:
            return self._results.pop(0)
        return None

    def fetchall(self) -> list[dict]:
        """Fetch all result rows.

        Returns:
            List of rows as dicts
        """
        results = self._results
        self._results = []
        return results
