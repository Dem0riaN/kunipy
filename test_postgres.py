"""Test PostgreSQL database integration."""

import asyncio
import uuid
from datetime import datetime, UTC

from src.infrastructure.memory.postgres_database import PostgreSQLDatabase
from src.infrastructure.memory.universal_db_adapter import UniversalDBAdapter
from src.infrastructure.memory.conversation_repository import ConversationRepository
from src.infrastructure.memory.user_chat_repository import UserRepository, ChatRepository
from src.infrastructure.memory.working_memory_repository import WorkingMemoryRepository
from src.domain.memory_models import ConversationMessage, WorkingMemoryItem


async def main():
    """Test PostgreSQL memory system."""
    try:
        print("=== PostgreSQL Memory System Test ===\n")

        # Connection string
        connection_string = "postgresql://kunipy:kunipy@localhost:5432/kunipy"
        print(f"Connecting to: {connection_string}")

        # Initialize database
        db = PostgreSQLDatabase(connection_string)
        pg_conn = await db.connect()
        print("✓ Connected to PostgreSQL\n")

        # Initialize schema
        await db.initialize_schema()
        print("✓ Schema initialized\n")

        # Wrap connection with universal adapter
        conn = UniversalDBAdapter(pg_conn)

        # Create repositories
        user_repo = UserRepository(conn)
        chat_repo = ChatRepository(conn)
        conversation_repo = ConversationRepository(conn)
        working_memory_repo = WorkingMemoryRepository(conn)
        print("✓ Repositories created\n")

        # Test user creation
        print("--- Testing User Creation ---")
        user = await user_repo.get_or_create_user(
            user_id="telegram:99999",
            display_name="test_user_postgres"
        )
        print(f"✓ User created: id={user.user_id}, name={user.display_name}\n")

        # Test chat creation
        print("--- Testing Chat Creation ---")
        chat = await chat_repo.get_or_create_chat(
            chat_id="telegram:88888",
            chat_type="private",
            title="Test Chat"
        )
        print(f"✓ Chat created: id={chat.chat_id}, type={chat.chat_type}\n")

        # Test message storage
        print("--- Testing Message Storage ---")
        msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            user_id=user.user_id,
            chat_id=chat.chat_id,
            channel="telegram",
            timestamp=datetime.now(UTC),
            role="user",
            content="Hello PostgreSQL!",
            metadata={"test": True}
        )
        await conversation_repo.store_message(msg)
        print(f"✓ Message stored: id={msg.message_id}\n")

        # Test message retrieval
        print("--- Testing Message Retrieval ---")
        history = await conversation_repo.get_conversation_history(
            user_id=user.user_id,
            chat_id=chat.chat_id,
            limit=10
        )
        print(f"✓ Retrieved {len(history)} message(s)")
        for i, m in enumerate(reversed(history), 1):
            print(f"   {i}. [{m.role}] {m.content[:50]}")
        print()

        # Test working memory
        print("--- Testing Working Memory ---")
        promise_item = WorkingMemoryItem(
            id=str(uuid.uuid4()),
            item_type="promise",
            content="Test PostgreSQL promise",
            status="active",
            priority=0
        )
        promise_id = await working_memory_repo.add_item(
            user_id=user.user_id,
            chat_id=chat.chat_id,
            channel="telegram",
            item=promise_item
        )
        print(f"✓ Promise added: id={promise_id}\n")

        # Get working memory context
        context = await working_memory_repo.get_context(
            user_id=user.user_id,
            chat_id=chat.chat_id,
            channel="telegram"
        )
        print(f"✓ Working memory context: {len(context.promises)} promise(s)\n")

        # Close connection
        await db.close()
        print("✓ Connection closed\n")

        print("========================================")
        print("✅ PostgreSQL Test Completed Successfully!")
        print("========================================")
        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
