"""Debug working memory insertion."""

import asyncio
import uuid
from datetime import datetime, UTC

from src.infrastructure.memory.postgres_database import PostgreSQLDatabase
from src.infrastructure.memory.universal_db_adapter import UniversalDBAdapter
from src.infrastructure.memory.working_memory_repository import WorkingMemoryRepository
from src.domain.memory_models import WorkingMemoryItem

async def main():
    """Debug working memory."""
    connection_string = "postgresql://kunipy:kunipy@localhost:5432/kunipy"

    # Connect
    db = PostgreSQLDatabase(connection_string)
    pg_conn = await db.connect()
    await db.initialize_schema()

    conn = UniversalDBAdapter(pg_conn)
    repo = WorkingMemoryRepository(conn)

    print("Creating working memory context...")

    # First ensure context exists
    await repo.update_context(
        user_id="test:user",
        chat_id="test:chat",
        channel="test",
        updates={}
    )

    # Check what ID was created
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM working_memory WHERE user_id = %s AND chat_id = %s AND channel = %s",
        ("test:user", "test:chat", "test")
    )
    row = cursor.fetchone()
    print(f"Working memory ID: {row}")

    # Create item
    item = WorkingMemoryItem(
        id=str(uuid.uuid4()),
        item_type="promise",
        content="Test promise",
        status="active",
        priority=0
    )

    print(f"\nAdding item with id={item.id}")
    print(f"Item type: {type(item.id)}")

    try:
        item_id = await repo.add_item(
            user_id="test:user",
            chat_id="test:chat",
            channel="test",
            item=item
        )
        print(f"✓ Item added: {item_id}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
