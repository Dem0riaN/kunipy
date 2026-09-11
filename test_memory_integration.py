"""Integration test for memory system with message flow."""

import asyncio
import uuid
from datetime import datetime, UTC
from pathlib import Path

from src.infrastructure.memory.database import MemoryDatabase
from src.infrastructure.memory.conversation_repository import ConversationRepository
from src.infrastructure.memory.memory_repository import MemoryRepository
from src.infrastructure.memory.working_memory_repository import WorkingMemoryRepository
from src.infrastructure.memory.user_chat_repository import UserRepository, ChatRepository
from src.infrastructure.memory.memory_service import MemoryService
from src.config import load_config

async def main():
    """Test memory system integration with message flow."""
    try:
        print("=== Memory System Integration Test ===\n")

        # Initialize database
        db_path = Path("data/test_integration.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"✓ Creating database at {db_path}")
        memory_db = MemoryDatabase(db_path)
        conn = memory_db.connect()
        memory_db.initialize_schema()
        print(f"✓ Database schema initialized\n")

        # Create repositories
        conversation_repo = ConversationRepository(conn)
        memory_repo = MemoryRepository(conn)
        working_memory_repo = WorkingMemoryRepository(conn)
        user_repo = UserRepository(conn)
        chat_repo = ChatRepository(conn)

        # Load config for embedding provider (stub)
        config = load_config("config.toml")

        # Create memory service (without real embedding provider for now)
        memory_service = MemoryService(
            conversation_repo=conversation_repo,
            memory_repo=memory_repo,
            working_memory_repo=working_memory_repo,
            user_repo=user_repo,
            chat_repo=chat_repo,
            embedding_provider=None,  # Skip embeddings for this test
            config=config,
        )
        print(f"✓ MemoryService initialized\n")

        # Simulate telegram message flow
        print("--- Simulating Message Flow ---\n")

        # User sends message
        print("1. User sends message")
        await memory_service.store_message(
            user_id="telegram:12345",
            chat_id="telegram:67890",
            channel="telegram",
            role="user",
            content="Hello! How are you?",
            metadata={"is_voice": False}
        )
        print("   ✓ User message stored\n")

        # Bot responds
        print("2. Bot responds")
        await memory_service.store_message(
            user_id="telegram:67890",  # Chat ID as user for bot
            chat_id="telegram:67890",
            channel="telegram",
            role="assistant",
            content="I'm doing well, thank you for asking!",
            metadata={"has_tool_calls": False}
        )
        print("   ✓ Assistant message stored\n")

        # User asks another question
        print("3. User asks follow-up")
        await memory_service.store_message(
            user_id="telegram:12345",
            chat_id="telegram:67890",
            channel="telegram",
            role="user",
            content="What's the weather like?",
            metadata={}
        )
        print("   ✓ User message stored\n")

        # Verify conversation history
        print("--- Verifying Conversation History ---\n")
        history = await conversation_repo.get_conversation_history(
            user_id="telegram:12345",
            chat_id="telegram:67890",
            limit=10
        )
        print(f"✓ Retrieved {len(history)} messages from conversation history")

        for i, msg in enumerate(reversed(history), 1):
            role_icon = "👤" if msg.role == "user" else "🤖"
            content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            print(f"   {i}. {role_icon} {msg.role}: {content_preview}")

        print(f"\n--- Testing Working Memory ---\n")

        # Add promise
        promise_id = await memory_service.add_promise(
            user_id="telegram:12345",
            chat_id="telegram:67890",
            channel="telegram",
            promise="Check weather and reply back"
        )
        print(f"✓ Promise added: {promise_id}")

        # Get working memory context
        context = await working_memory_repo.get_context(
            user_id="telegram:12345",
            chat_id="telegram:67890",
            channel="telegram"
        )
        print(f"✓ Working memory context: {len(context.promises)} promise(s)")

        print(f"\n✅ Integration test completed successfully!")
        print(f"\nSummary:")
        print(f"  - Messages stored: {len(history)}")
        print(f"  - Promises tracked: {len(context.promises)}")
        print(f"  - Database: {db_path}")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
