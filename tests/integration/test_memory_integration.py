"""Integration tests for memory system with DI container.

Tests that memory components (MemoryStore, WorkingMemory, EmbeddingCache)
are properly wired in the DI container and work together.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.config import Config
from src.di.container import create_dependencies
from src.domain.memory.models import MemoryKind, MemoryPiece, MemoryScope


@pytest.fixture
async def temp_config():
    """Create temporary config for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.config import Endpoint, EndpointAndModel, LockdownMode

        config = Config(
            # LLM config
            llm=EndpointAndModel(
                endpoint=Endpoint(
                    base_url="http://localhost:11434/v1/",
                    bearer_key="test-key",
                ),
                model="gpt-4",
            ),
            # Character
            character_name="TestKuni",
            # Telegram disabled for tests
            telegram_enabled=False,
            telegram_api_id=0,
            telegram_api_hash="",
            telegram_phone="",
            telegram_database_directory="",
            # Diary disabled for tests
            diary_enabled=False,
            diary_dir=str(Path(tmpdir) / "diary"),
            diary_min_relatedness=0.5,
            # Lockdown
            lockdown=LockdownMode.NONE,
            papik_chat_id=0,
            # Capabilities
            capability_hearing=False,
            capability_vision=False,
            capability_web_search=False,
            capability_generate_images=False,
        )
        yield config, Path(tmpdir)


@pytest.mark.asyncio
async def test_di_container_memory_integration(temp_config):
    """Test that DI container properly wires memory components."""
    config, working_dir = temp_config

    # Create dependencies
    deps = await create_dependencies(working_dir, config)

    # Verify memory store is not None
    assert deps.memory_store is not None, "memory_store should be wired"

    # Verify working memory is not None
    assert deps.working_memory is not None, "working_memory should be wired"

    # Verify they are not stub implementations
    from src.infrastructure.memory import MemoryStore, WorkingMemory

    assert isinstance(deps.memory_store, MemoryStore), "Should use MemoryStore, not stub"
    assert isinstance(deps.working_memory, WorkingMemory), "Should use WorkingMemory, not stub"


@pytest.mark.asyncio
async def test_memory_store_basic_operations(temp_config):
    """Test basic CRUD operations on MemoryStore through DI."""
    config, working_dir = temp_config

    deps = await create_dependencies(working_dir, config)

    # Create a test memory
    memory = MemoryPiece(
        content="Test memory content",
        user_id="123456789",
        chat_id="987654321",
        scope=MemoryScope.DIALOGUE,
        kind=MemoryKind.FACTUAL,
        confidence=0.9,
        importance=0.8,
    )

    # Store memory
    memory_id = await deps.memory_store.create_memory(memory)
    assert memory_id is not None, "Should return memory ID"

    # Retrieve memory
    retrieved = await deps.memory_store.get_memory(memory_id)
    assert retrieved is not None, "Should retrieve stored memory"
    assert retrieved.content == memory.content
    assert retrieved.user_id == memory.user_id
    assert retrieved.confidence == memory.confidence


@pytest.mark.asyncio
async def test_working_memory_operations(temp_config):
    """Test WorkingMemory operations through DI."""
    config, working_dir = temp_config

    deps = await create_dependencies(working_dir, config)

    user_id = "123456789"
    chat_id = "987654321"

    # Get initial context (should be empty)
    context = deps.working_memory.get_context(user_id, chat_id)
    assert context is not None
    assert len(context.recent_messages) == 0

    # Update context
    deps.working_memory.update_context(
        user_id=user_id,
        chat_id=chat_id,
        message_text="Test message",
    )

    # Verify update
    updated_context = deps.working_memory.get_context(user_id, chat_id)
    assert len(updated_context.recent_messages) == 1
    assert updated_context.recent_messages[0] == "Test message"


@pytest.mark.asyncio
async def test_memory_search_integration(temp_config):
    """Test memory search through DI container."""
    config, working_dir = temp_config

    deps = await create_dependencies(working_dir, config)

    # Create multiple memories
    memories = [
        MemoryPiece(
            content=f"Test memory {i}",
            user_id="123456789",
            chat_id="987654321",
            scope=MemoryScope.DIALOGUE,
            kind=MemoryKind.FACTUAL,
            confidence=0.8,
            importance=0.7,
        )
        for i in range(3)
    ]

    # Store all memories
    for memory in memories:
        await deps.memory_store.create_memory(memory)

    # Search by user
    results = await deps.memory_store.search_by_user(
        user_id="123456789",
        limit=10,
    )

    assert len(results) == 3, "Should find all 3 memories"


@pytest.mark.asyncio
async def test_chroma_persistence(temp_config):
    """Test that ChromaDB persists data correctly."""
    config, working_dir = temp_config

    # Create first DI instance
    deps1 = await create_dependencies(working_dir, config)

    # Create and store memory
    memory = MemoryPiece(
        content="Persistent test memory",
        user_id="123456789",
        chat_id="987654321",
        scope=MemoryScope.PERSONAL,
        kind=MemoryKind.FACTUAL,
        confidence=0.95,
        importance=0.85,
    )

    memory_id = await deps1.memory_store.create_memory(memory)

    # Create second DI instance (simulates restart)
    deps2 = await create_dependencies(working_dir, config)

    # Retrieve from second instance
    retrieved = await deps2.memory_store.get_memory(memory_id)
    assert retrieved is not None, "Memory should persist across instances"
    assert retrieved.content == memory.content


if __name__ == "__main__":
    # Run tests
    asyncio.run(pytest.main([__file__, "-v"]))
