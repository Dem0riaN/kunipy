"""Migration script from SQLite to PostgreSQL (ТЗ-002)."""

import asyncio
import json
import sqlite3
from pathlib import Path

import psycopg


async def migrate_sqlite_to_postgres(
    sqlite_path: str,
    postgres_url: str
) -> None:
    """Migrate data from SQLite to PostgreSQL.

    Args:
        sqlite_path: Path to SQLite database file
        postgres_url: PostgreSQL connection string
    """
    print(f"=== Migrating from SQLite to PostgreSQL ===\n")
    print(f"Source: {sqlite_path}")
    print(f"Target: {postgres_url}\n")

    # Check if SQLite database exists
    if not Path(sqlite_path).exists():
        print(f"✗ SQLite database not found at {sqlite_path}")
        print("No data to migrate.")
        return

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = await psycopg.AsyncConnection.connect(postgres_url, autocommit=True)

    print("✓ Connected to both databases\n")

    # Tables to migrate (in dependency order)
    tables = [
        "users",
        "chats",
        "conversations",
        "memories",
        "memory_embeddings",
        "working_memory",
        "working_memory_items",
        "memory_links",
        "memory_tags",
        "user_preferences",
    ]

    total_rows = 0

    for table in tables:
        print(f"Migrating table: {table}")

        # Check if table exists in SQLite
        sqlite_cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if not sqlite_cur.fetchone():
            print(f"  ⚠ Table '{table}' not found in SQLite, skipping\n")
            continue

        # Get all rows from SQLite
        sqlite_cur.execute(f"SELECT * FROM {table}")
        rows = sqlite_cur.fetchall()

        if not rows:
            print(f"  ✓ No data to migrate (0 rows)\n")
            continue

        # Get column names
        columns = [description[0] for description in sqlite_cur.description]

        # Prepare INSERT statement for PostgreSQL
        placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
        insert_sql = f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
        """

        # Insert rows into PostgreSQL
        async with pg_conn.cursor() as pg_cur:
            for row in rows:
                values = []
                for value in row:
                    # Convert SQLite types to PostgreSQL types
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        # Try to parse as JSON for metadata fields
                        try:
                            values.append(json.loads(value))
                        except json.JSONDecodeError:
                            values.append(value)
                    else:
                        values.append(value)

                try:
                    await pg_cur.execute(insert_sql, tuple(values))
                except Exception as e:
                    print(f"  ⚠ Error inserting row: {e}")
                    continue

        row_count = len(rows)
        total_rows += row_count
        print(f"  ✓ Migrated {row_count} row(s)\n")

    # Close connections
    sqlite_conn.close()
    await pg_conn.close()

    print("========================================")
    print(f"✅ Migration Complete!")
    print(f"Total rows migrated: {total_rows}")
    print("========================================")


async def main():
    """Run migration."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python migrate_to_postgres.py <sqlite_path> <postgres_url>")
        print("\nExample:")
        print("  python migrate_to_postgres.py data/memory.db postgresql://kunipy:kunipy@localhost:5432/kunipy")
        sys.exit(1)

    sqlite_path = sys.argv[1]
    postgres_url = sys.argv[2]

    try:
        await migrate_sqlite_to_postgres(sqlite_path, postgres_url)
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
