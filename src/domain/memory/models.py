"""Memory domain models (ТЗ-002).

Foundation for multi-level memory system.
Full implementation in Phase 2.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryScope(Enum):
    """Memory visibility scope (ТЗ-002 punkt 15)."""
    PRIVATE = "private"
    USER = "user"
    CHAT = "chat"
    SHARED = "shared"
    GLOBAL = "global"


class MemoryKind(Enum):
    """Memory piece type (ТЗ-002 punkt 10)."""
    ENTITY_DESCRIPTION = "entity_description"
    THOUGHT = "thought"
    EVENT = "event"
    FACT = "fact"
    OTHER = "other"


@dataclass
class MemoryPiece:
    """Memory piece model (ТЗ-002 punkt 9).

    Based on C++ kuni Diary::EntryEx.
    """
    id: str
    kind: MemoryKind
    content: str

    # Confidence model (like C++ kuni)
    confidence: float  # -1 (lie) to 0 (theory) to 1 (ground truth)
    importance: float  # 0.0 to 1.0

    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_used: datetime
    usage_count: int

    # Semantic search
    embedding: list[float]
    retrieval_cues: list[str] = field(default_factory=list)

    # Scope and visibility
    scope: MemoryScope = MemoryScope.GLOBAL
    user_id: str | None = None
    chat_id: str | None = None
    channel: str | None = None

    # Provenance (ТЗ-002 punkt 21)
    source_message_ids: list[str] = field(default_factory=list)
    source_type: str | None = None  # "conversation", "consolidation", "migration"

    # Relationships
    entities: list[str] = field(default_factory=list)
    related_memory_ids: list[str] = field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Promise:
    """Promise made by character (ТЗ-002 punkt 34)."""
    id: str
    content: str
    to_user_id: str
    created_at: datetime
    deadline: datetime | None = None
    fulfilled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Plan or intention (ТЗ-002 punkt 34)."""
    id: str
    description: str
    created_at: datetime
    steps: list[str] = field(default_factory=list)
    target_date: datetime | None = None
    completed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingMemoryContext:
    """Working memory context (ТЗ-002 punkt 7.6).

    Current state of interaction, not persisted long-term.
    """
    user_id: str
    chat_id: str
    channel: str

    # Current conversation state
    current_topic: str | None = None
    conversation_summary: str | None = None
    recent_entities: list[str] = field(default_factory=list)

    # Pending items
    pending_questions: list[str] = field(default_factory=list)
    promises: list[Promise] = field(default_factory=list)
    plans: list[Plan] = field(default_factory=list)

    # Temporal state
    last_interaction: datetime | None = None
    emotion_state: str | None = None

    # Context metadata
    metadata: dict[str, Any] = field(default_factory=dict)
