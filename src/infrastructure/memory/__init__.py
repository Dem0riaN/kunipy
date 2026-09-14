"""Memory infrastructure."""

# ТЗ-002 new memory system
from .conversation_repository import ConversationRepository
from .database import MemoryDatabase

# Phase 4: Diary auto-RAG injection
from .diary_context_injector import DiaryContextInjector
from .diary_dump_service import DiaryDumpService
from .diary_file_store import DiaryFileStore

# Phase 1: Diary stores (ChromaDB + file I/O)
from .diary_vector_store import DiaryVectorStore
from .embedding_cache import EmbeddingCache
from .memory_link_repository import MemoryLinkRepository
from .memory_repository import MemoryRepository
from .memory_service import MemoryService
from .memory_tag_repository import MemoryTagRepository

# Phase 2: Sleep consolidation
from .sleep_consolidation import SleepConsolidationService
from .storage import MemoryStore
from .stub_store import InMemoryStore, InMemoryWorkingMemory

# Phase 3: Working Memory + Diary Pipeline
from .token_counter import TokenCounter
from .user_chat_repository import ChatRepository, UserRepository
from .user_preference_repository import UserPreferenceRepository
from .vector_store import VectorStore
from .working_memory import WorkingMemory
from .working_memory_file_store import WorkingMemoryFileStore

__all__ = [
    "EmbeddingCache",
    "InMemoryStore",
    "InMemoryWorkingMemory",
    "MemoryStore",
    "VectorStore",
    "WorkingMemory",
    # Phase 1: Diary stores
    "DiaryVectorStore",
    "DiaryFileStore",
    # Phase 3: Working Memory + Diary Pipeline
    "TokenCounter",
    "DiaryDumpService",
    "WorkingMemoryFileStore",
    # Phase 4: Diary auto-RAG injection
    "DiaryContextInjector",
    # Phase 2: Sleep consolidation
    "SleepConsolidationService",
    # ТЗ-002
    "MemoryDatabase",
    "ConversationRepository",
    "MemoryRepository",
    "MemoryLinkRepository",
    "UserPreferenceRepository",
    "MemoryTagRepository",
    "UserRepository",
    "ChatRepository",
    "MemoryService",
]
