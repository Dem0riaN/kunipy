"""Memory interface protocols (ТЗ-002 foundation)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class MemoryScope(Enum):
    """Memory visibility scope (ТЗ-002 punkt 15).

    Defines who can access this memory piece:
    - PRIVATE: Only internal to character
    - USER: Specific user across all chats
    - CHAT: Specific chat only
    - SHARED: Multiple users (with permission)
    - GLOBAL: Character's general knowledge
    """
    PRIVATE = "private"
    USER = "user"
    CHAT = "chat"
    SHARED = "shared"
    GLOBAL = "global"


class MemoryKind(Enum):
    """Memory piece type (ТЗ-002 punkt 10).

    Based on original kuni C++ implementation.
    """
    ENTITY_DESCRIPTION = "entity_description"
    THOUGHT = "thought"
    EVENT = "event"
    FACT = "fact"
    OTHER = "other"


@dataclass
class MemoryPiece:
    """Memory piece model (ТЗ-002 punkt 9).

    Core unit of long-term memory storage.
    """
    id: str
    kind: MemoryKind
    content: str
    confidence: float  # -1 (lie) to 0 (theory) to 1 (ground truth)
    importance: float  # 0.0 to 1.0
    created_at: datetime
    updated_at: datetime
    last_used: datetime
    usage_count: int
    embedding: list[float]
    scope: MemoryScope

    # Context information
    user_id: str | None = None
    chat_id: str | None = None
    channel: str | None = None  # "telegram", "desktop", "voice"

    # Provenance (ТЗ-002 punkt 21)
    source_message_ids: list[str] = field(default_factory=list)
    source_type: str | None = None  # "conversation", "consolidation", "migration"

    # Metadata
    retrieval_cues: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingMemoryContext:
    """Working memory context (ТЗ-002 punkt 7.6).

    Current state of interaction, not persisted long-term.
    """
    user_id: str
    chat_id: str
    channel: str

    # Current state
    current_topic: str | None = None
    conversation_summary: str | None = None

    # Pending items
    pending_questions: list[str] = field(default_factory=list)
    promises: list[dict[str, Any]] = field(default_factory=list)
    plans: list[dict[str, Any]] = field(default_factory=list)

    # Temporal state
    last_interaction: datetime | None = None
    emotion_state: str | None = None

    # Context metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class IMemoryStore(Protocol):
    """Protocol for memory storage operations (ТЗ-002 punkt 38).

    Implementation deferred to Phase 2.
    """

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Create new memory piece.

        Args:
            piece: Memory piece to store

        Returns:
            Memory ID
        """
        ...

    async def get_memory(self, memory_id: str) -> MemoryPiece | None:
        """Retrieve memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory piece if found
        """
        ...

    async def update_memory(self, piece: MemoryPiece) -> bool:
        """Update existing memory piece.

        Args:
            piece: Updated memory piece

        Returns:
            True if successful
        """
        ...

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory piece.

        Args:
            memory_id: Memory ID

        Returns:
            True if deleted
        """
        ...

    async def search_memory(
        self,
        query_embedding: list[float],
        scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 10,
        min_confidence: float = -1.0
    ) -> list[MemoryPiece]:
        """Search memory by embedding similarity.

        Implements semantic search with scope filtering.

        Args:
            query_embedding: Query vector
            scope: Memory scope filter
            user_id: Filter by user
            chat_id: Filter by chat
            limit: Maximum results
            min_confidence: Minimum confidence threshold

        Returns:
            Ranked list of memory pieces
        """
        ...

    async def search_by_user(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search user-specific memory.

        Args:
            user_id: User ID
            query_embedding: Query vector
            limit: Maximum results

        Returns:
            Ranked list of user memories
        """
        ...

    async def search_by_chat(
        self,
        chat_id: str,
        query_embedding: list[float],
        limit: int = 10
    ) -> list[MemoryPiece]:
        """Search chat-specific memory.

        Args:
            chat_id: Chat ID
            query_embedding: Query vector
            limit: Maximum results

        Returns:
            Ranked list of chat memories
        """
        ...


class IWorkingMemory(Protocol):
    """Protocol for working memory operations (ТЗ-002 punkt 7.6).

    Manages current interaction state (not long-term storage).
    Implementation deferred to Phase 2.
    """

    async def get_context(
        self,
        user_id: str,
        chat_id: str
    ) -> WorkingMemoryContext:
        """Get current working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID

        Returns:
            Current context (creates empty if doesn't exist)
        """
        ...

    async def update_context(
        self,
        user_id: str,
        chat_id: str,
        updates: dict[str, Any]
    ) -> None:
        """Update working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID
            updates: Fields to update
        """
        ...

    async def add_promise(
        self,
        user_id: str,
        chat_id: str,
        promise: str
    ) -> None:
        """Add promise to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            promise: Promise description
        """
        ...

    async def add_plan(
        self,
        user_id: str,
        chat_id: str,
        plan: dict[str, Any]
    ) -> None:
        """Add plan to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            plan: Plan details
        """
        ...

    async def clear_context(
        self,
        user_id: str,
        chat_id: str
    ) -> None:
        """Clear working memory for context.

        Args:
            user_id: User ID
            chat_id: Chat ID
        """
        ...
