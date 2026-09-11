"""Memory infrastructure."""

from .embedding_cache import EmbeddingCache
from .storage import MemoryStore
from .stub_store import InMemoryStore, InMemoryWorkingMemory
from .vector_store import VectorStore
from .working_memory import WorkingMemory

# ТЗ-002 new memory system
from .conversation_repository import ConversationRepository
from .database import MemoryDatabase
from .memory_repository import MemoryRepository
from .memory_service import MemoryService
from .postgres_adapter import PostgreSQLAdapter
from .postgres_database import PostgreSQLDatabase
from .user_chat_repository import ChatRepository, UserRepository
from .working_memory_repository import WorkingMemoryRepository

__all__ = [
    "EmbeddingCache",
    "InMemoryStore",
    "InMemoryWorkingMemory",
    "MemoryStore",
    "VectorStore",
    "WorkingMemory",
    # ТЗ-002
    "MemoryDatabase",
    "PostgreSQLDatabase",
    "PostgreSQLAdapter",
    "ConversationRepository",
    "MemoryRepository",
    "WorkingMemoryRepository",
    "UserRepository",
    "ChatRepository",
    "MemoryService",
]
