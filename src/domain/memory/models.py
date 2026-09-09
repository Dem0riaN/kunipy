"""Memory domain models (ТЗ-002).

Foundation for multi-level memory system.
Full implementation in Phase 2.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum


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
    embedding: List[float]
    retrieval_cues: List[str] = field(default_factory=list)

    # Scope and visibility
    scope: MemoryScope = MemoryScope.GLOBAL
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    channel: Optional[str] = None

    # Provenance (ТЗ-002 punkt 21)
    source_message_ids: List[str] = field(default_factory=list)
    source_type: Optional[str] = None  # "conversation", "consolidation", "migration"

    # Relationships
    entities: List[str] = field(default_factory=list)
    related_memory_ids: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Promise:
    """Promise made by character (ТЗ-002 punkt 34)."""
    id: str
    content: str
    to_user_id: str
    created_at: datetime
    deadline: Optional[datetime] = None
    fulfilled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Plan or intention (ТЗ-002 punkt 34)."""
    id: str
    description: str
    steps: List[str] = field(default_factory=list)
    created_at: datetime
    target_date: Optional[datetime] = None
    completed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingMemoryContext:
    """Working memory context (ТЗ-002 punkt 7.6).

    Current state of interaction, not persisted long-term.
    """
    user_id: str
    chat_id: str
    channel: str

    # Current conversation state
    current_topic: Optional[str] = None
    conversation_summary: Optional[str] = None
    recent_entities: List[str] = field(default_factory=list)

    # Pending items
    pending_questions: List[str] = field(default_factory=list)
    promises: List[Promise] = field(default_factory=list)
    plans: List[Plan] = field(default_factory=list)

    # Temporal state
    last_interaction: Optional[datetime] = None
    emotion_state: Optional[str] = None

    # Context metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
