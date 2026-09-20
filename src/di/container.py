"""Dependency Injection container.

Replaces singleton pattern with explicit dependency graph.
Based on C++ kuni Init struct pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import Config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..application.media.registry import MediaExtractorRegistry
    from ..diary import Diary
    from ..infrastructure.memory import (
        DiaryContextInjector,
        DiaryDumpService,
        MemoryService,
        SleepConsolidationService,
    )
    from ..infrastructure.memory.memory_formation import MemoryFormationService

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

    # Media extraction (ТЗ-005)
    extractor_registry: MediaExtractorRegistry

    # Legacy components (to be refactored)
    diary: Diary | None = None  # Will be refactored to use IMemoryStore

    # Phase 3: Conversation→diary pipeline
    diary_dump_service: DiaryDumpService | None = None

    # Phase 4: Diary auto-RAG injection
    diary_context_injector: DiaryContextInjector | None = None

    # Phase 2: Sleep consolidation
    consolidation_service: SleepConsolidationService | None = None

    # ТЗ-002 new memory system
    memory_service: MemoryService | None = None  # New high-level memory API
    memory_formation: MemoryFormationService | None = None  # Automatic memory extraction

    # Working memory update service (autonomy restoration)
    working_memory_update_service: Any | None = None  # WorkingMemoryUpdateService

    # Proxy server handle (for graceful shutdown, set by App._start_proxy_server)
    _proxy_server: Any | None = None


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
    from ..infrastructure.embedding_adapter import OpenAIChatEmbeddingAdapter

    # Memory infrastructure (ТЗ-001 memory system)
    from ..infrastructure.memory import EmbeddingCache, MemoryStore, WorkingMemory
    from ..notification_manager import NotificationManager
    from ..openai_chat import OpenAIChat
    from ..telegram_client import TelegramClient

    # Create instances in dependency order

    # LLM layer
    openai_chat = OpenAIChat(
        endpoint=config.llm,
        timeout=30,
        max_retries=2,
    )

    # Embedding provider (separate endpoint for embeddings)
    # If embedding config is empty, fallback to main LLM
    embedding_endpoint = config.embedding if config.embedding.model else config.llm
    embedding_openai = OpenAIChat(
        endpoint=embedding_endpoint,
        timeout=30,
        max_retries=2,
    )
    # Wrap in adapter to match IEmbeddingProvider protocol
    embedding_provider = OpenAIChatEmbeddingAdapter(embedding_openai)

    # Telegram layer (only if enabled)
    telegram_client = None
    if config.telegram_enabled:
        telegram_client = TelegramClient(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            database_dir=config.telegram_database_directory,
        )
        # Увеличенные таймауты для нестабильного подключения
        await telegram_client.start(connect_timeout=120.0, max_retries=10)

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

    # Memory layer (ChromaDB-based implementation, ТЗ-001 complete)
    chroma_persist_dir = working_dir / "chroma"
    chroma_persist_dir.mkdir(parents=True, exist_ok=True)

    # Initialize embedding cache (TTL-based, reduces API calls)
    _ = EmbeddingCache(ttl_seconds=3600)  # TODO: wire with embedding_provider

    memory_store = MemoryStore(persist_directory=str(chroma_persist_dir))

    # WorkingMemory with file persistence (Phase 3)
    from ..infrastructure.memory import WorkingMemoryFileStore
    wm_file_store = WorkingMemoryFileStore(working_dir / "working_memory.md")
    working_memory = WorkingMemory(file_store=wm_file_store)

    # Worker notification manager
    notification_manager = NotificationManager()

    # Media extractor registry (ТЗ-005)
    from ..application.media.registry import MediaExtractorRegistry
    from ..application.media.txt_extractor import TxtExtractor

    extractor_registry = MediaExtractorRegistry()

    # Register TxtExtractor with config limits
    txt_extractor = TxtExtractor(
        max_size_bytes=config.document_max_size_bytes,
        max_context_chars=config.document_max_context_chars
    )
    extractor_registry.register(txt_extractor)

    # Legacy diary with Phase 1 stores + Phase 3 dump service
    diary = None
    diary_dump_service = None
    diary_context_injector = None
    consolidation_service = None
    if config.diary_enabled:
        from ..infrastructure.memory import (
            DiaryDumpService,
            DiaryFileStore,
            DiaryVectorStore,
            TokenCounter,
        )

        # Phase 1: Core stores for diary
        diary_chroma_dir = working_dir / config.diary_chroma_dir
        diary_chroma_dir.mkdir(parents=True, exist_ok=True)
        diary_vector_store = DiaryVectorStore(str(diary_chroma_dir))
        diary_file_store = DiaryFileStore(Path(config.diary_dir))

        diary = Diary(
            diary_dir=Path(config.diary_dir),
            openai_chat=openai_chat,
            config=config,
            file_store=diary_file_store,
            vector_store=diary_vector_store,
        )
        await diary._migrate_legacy_entries()

        # Phase 3: Conversation→diary pipeline
        token_counter = TokenCounter()
        diary_dump_service = DiaryDumpService(
            diary=diary,
            openai_chat=openai_chat,
            config=config,
            token_counter=token_counter,
        )
        logger.info("Diary dump service initialized")

        # Phase 4: Auto-RAG injection
        from ..infrastructure.memory import DiaryContextInjector

        diary_context_injector = DiaryContextInjector(
            diary=diary,
            openai_chat=openai_chat,
            config=config,
        )
        logger.info("Diary context injector initialized")

        # Phase 2: Sleep consolidation
        from ..infrastructure.memory import SleepConsolidationService

        consolidation_service = SleepConsolidationService(
            diary=diary,
            openai_chat=openai_chat,
            config=config,
        )
        diary.set_consolidation_service(consolidation_service)
        logger.info("Sleep consolidation service initialized")

    # ТЗ-002 new memory system (if enabled)
    memory_service = None
    memory_formation = None
    if config.memory_enabled:
        from ..infrastructure.memory import (
            ChatRepository,
            ConversationRepository,
            MemoryDatabase,
            MemoryLinkRepository,
            MemoryRepository,
            MemoryService,
            MemoryTagRepository,
            UserPreferenceRepository,
            UserRepository,
        )
        from ..infrastructure.memory.memory_formation import MemoryFormationService

        # SQLite only (PostgreSQL path removed — see plan dapper-swinging-candy)
        memory_db_path = working_dir / config.memory_db_path
        memory_db = MemoryDatabase(memory_db_path)
        sqlite_conn = memory_db.connect()  # WAL + busy_timeout=5000 set inside
        memory_db.initialize_schema()

        # Create repositories (all backed by the same SQLite connection)
        conversation_repo = ConversationRepository(sqlite_conn)
        memory_repo = MemoryRepository(
            sqlite_conn, embedding_model=config.embedding.model or "default"
        )
        memory_link_repo = MemoryLinkRepository(sqlite_conn)
        user_preference_repo = UserPreferenceRepository(sqlite_conn)
        memory_tag_repo = MemoryTagRepository(sqlite_conn)
        user_repo = UserRepository(sqlite_conn)
        chat_repo = ChatRepository(sqlite_conn)

        # Create high-level service with ChromaDB MemoryStore for vector search
        memory_service = MemoryService(
            memory_store=memory_store,  # ChromaDB from L174
            conversation_repo=conversation_repo,
            memory_repo=memory_repo,
            memory_link_repo=memory_link_repo,
            user_preference_repo=user_preference_repo,
            memory_tag_repo=memory_tag_repo,
            user_repo=user_repo,
            chat_repo=chat_repo,
            working_memory=working_memory,  # in-memory + .md
            embedding_provider=embedding_provider,
            config=config,
        )

        # Create memory formation service for automatic extraction
        memory_formation = MemoryFormationService(
            llm_client=openai_chat,
            config=config,
        )

    # Working memory update service (autonomy restoration)
    from ..application.working_memory_update_service import WorkingMemoryUpdateService
    working_memory_update_service = WorkingMemoryUpdateService(
        working_memory=working_memory,
        openai_chat=openai_chat,
        config=config,
    )
    logger.info("Working memory update service initialized")

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
        extractor_registry=extractor_registry,
        memory_service=memory_service,
        memory_formation=memory_formation,
        diary_dump_service=diary_dump_service,
        diary_context_injector=diary_context_injector,
        consolidation_service=consolidation_service,
        working_memory_update_service=working_memory_update_service,
    )
