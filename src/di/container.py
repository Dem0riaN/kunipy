"""Dependency Injection container.

Replaces singleton pattern with explicit dependency graph.
Based on C++ kuni Init struct pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import Config

if TYPE_CHECKING:
    from ..diary import Diary

from ..interfaces import (
    IEmbeddingProvider,
    IMemoryStore,
    IMessageDeliveryTracker,
    INotificationManager,
    IOpenAIChat,
    ITelegramClient,
    ITelegramMessageService,
    IWorkingMemory,
)


@dataclass
class Dependencies:
    """Central DI container.

    All application components receive dependencies through this container.
    This replaces the singleton pattern used in config.py and elsewhere.

    Based on C++ kuni dependency injection via Init structs.
    """

    # Configuration
    config: Config

    # Core LLM services
    openai_chat: IOpenAIChat
    embedding_provider: IEmbeddingProvider

    # Telegram layer
    telegram_client: ITelegramClient
    telegram_message_service: ITelegramMessageService

    # Memory layer (ТЗ-002 interfaces, stub implementations in Phase 1)
    memory_store: IMemoryStore
    working_memory: IWorkingMemory

    # Delivery tracking (ТЗ-001 punkt 12-18, stub implementation in Phase 1)
    delivery_tracker: IMessageDeliveryTracker

    # Worker management
    notification_manager: INotificationManager

    # Legacy components (to be refactored)
    diary: Diary | None = None  # Will be refactored to use IMemoryStore


async def create_dependencies(working_dir: Path, config: Config) -> Dependencies:
    """Factory function to create dependency graph.

    This is the composition root where all dependencies are wired together.
    Order matters: dependencies must be created before their dependents.

    REFACTORED: Accepts config as parameter instead of using singleton.

    Args:
        working_dir: Application working directory
        config: Application configuration (loaded from config.toml)

    Returns:
        Fully wired dependency container

    Example:
        >>> from config import load_config
        >>> config = load_config("config.toml")
        >>> deps = await create_dependencies(Path("data"), config)
        >>> worker = Worker(deps)
    """
    # Import here to avoid circular dependencies
    from ..diary import Diary

    # Stub implementations for worker management (replaced in Phase 2)
    from ..infrastructure.memory.stub_store import InMemoryStore, InMemoryWorkingMemory
    from ..notification_manager import NotificationManager
    from ..openai_chat import OpenAIChat
    from ..telegram_client import TelegramClient

    # Create instances in dependency order

    # LLM layer
    openai_chat = OpenAIChat(
        api_key=config.llm.endpoint.bearer_key,
        base_url=config.llm.endpoint.base_url,
        default_model=config.llm.model,
    )

    # Embedding provider (reuses OpenAI chat for now)
    embedding_provider = openai_chat  # OpenAIChat implements IEmbeddingProvider

    # Telegram layer (only if enabled)
    telegram_client = None
    if config.telegram_enabled:
        telegram_client = TelegramClient(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            phone=config.telegram_phone,
            database_directory=config.telegram_database_directory,
        )
        await telegram_client.start()

    # Delivery tracking (ТЗ-001 punkt 12-18)
    from ..infrastructure.delivery.storage import MessageDeliveryStorage
    from ..infrastructure.delivery.telegram_checker import TelegramMessageDeliveryChecker
    from ..infrastructure.delivery.tracker import MessageDeliveryTracker

    delivery_db_path = working_dir / "delivery.db"
    delivery_storage = MessageDeliveryStorage(delivery_db_path, config)
    await delivery_storage.initialize()

    delivery_checker = TelegramMessageDeliveryChecker(telegram_client) if telegram_client else None
    delivery_tracker = MessageDeliveryTracker(delivery_storage, delivery_checker) if delivery_checker else None

    # High-level Telegram service (will be created in Phase 1 refactoring)
    telegram_message_service = telegram_client  # type: ignore

    # Memory layer (stubs for Phase 1, full implementation in ТЗ-002)
    memory_store = InMemoryStore()
    working_memory = InMemoryWorkingMemory()

    # Worker notification manager
    notification_manager = NotificationManager()

    # Legacy diary (will be migrated to new memory system in ТЗ-002)
    diary = None
    if config.diary_enabled:
        diary = Diary(
            diary_dir=Path(config.diary_dir),
            openai_chat=openai_chat,
            config=config,
        )

    return Dependencies(
        config=config,
        openai_chat=openai_chat,
        embedding_provider=embedding_provider,
        telegram_client=telegram_client,
        telegram_message_service=telegram_message_service,
        memory_store=memory_store,
        working_memory=working_memory,
        delivery_tracker=delivery_tracker,
        notification_manager=notification_manager,
        diary=diary,
    )
