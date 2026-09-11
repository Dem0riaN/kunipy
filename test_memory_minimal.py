"""Minimal memory system test that avoids TDLib initialization."""

import sqlite3
from pathlib import Path

from src.infrastructure.memory.database import MemoryDatabase
from src.infrastructure.memory.conversation_repository import ConversationRepository
from src.infrastructure.memory.memory_repository import MemoryRepository
from src.infrastructure.memory.working_memory_repository import WorkingMemoryRepository
from src.infrastructure.memory.user_chat_repository import UserRepository, ChatRepository
from src.interfaces.memory import MemoryScope, MemoryKind
from src.domain.memory_models import WorkingMemoryItem

def main():
    """Test memory system components directly."""
    try:
        # Initialize database
        db_path = Path("data/test_memory.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"✓ Creating database at {db_path}")
        memory_db = MemoryDatabase(db_path)
        conn = memory_db.connect()
        memory_db.initialize_schema()
        print(f"✓ Database schema initialized")

        # Create repositories
        conversation_repo = ConversationRepository(conn)
        memory_repo = MemoryRepository(conn)
        working_memory_repo = WorkingMemoryRepository(conn)
        user_repo = UserRepository(conn)
        chat_repo = ChatRepository(conn)
        print(f"✓ All repositories created")

        # Test user creation
        import asyncio
        user = asyncio.run(user_repo.get_or_create_user(
            user_id="telegram:12345",
            display_name="test_user"
        ))
        print(f"✓ User created: id={user.user_id}, name={user.display_name}")

        # Test chat creation
        chat = asyncio.run(chat_repo.get_or_create_chat(
            chat_id="telegram:67890",
            chat_type="private",
            title=None
        ))
        print(f"✓ Chat created: id={chat.chat_id}, type={chat.chat_type}")

        # Test conversation message storage
        import uuid
        from datetime import datetime, UTC
        from src.domain.memory_models import ConversationMessage

        msg = ConversationMessage(
            message_id=str(uuid.uuid4()),
            user_id=user.user_id,
            chat_id=chat.chat_id,
            channel="telegram",
            timestamp=datetime.now(UTC),
            role="user",
            content="Test message",
            metadata={}
        )
        asyncio.run(conversation_repo.store_message(msg))
        print(f"✓ Message stored: id={msg.message_id}")

        # Test working memory
        promise_item = WorkingMemoryItem(
            id=str(uuid.uuid4()),
            item_type="promise",
            content="Test promise",
            status="active",
            priority=0
        )
        promise_id = asyncio.run(working_memory_repo.add_item(
            user_id=user.user_id,
            chat_id=chat.chat_id,
            channel="telegram",
            item=promise_item
        ))
        print(f"✓ Promise added: id={promise_id}")

        # Retrieve working memory context
        context = asyncio.run(working_memory_repo.get_context(user.user_id, chat.chat_id, "telegram"))
        print(f"✓ Retrieved working memory context with {len(context.promises)} promise(s)")

        print(f"\n✅ All memory system components working correctly!")
        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
