"""Domain models for memory system (ТЗ-002).

Extended models for conversation history, users, chats.
MemoryPiece and WorkingMemoryContext already defined in interfaces/memory.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class User:
    """User entity (ТЗ-002 punkt 4).

    Represents a person interacting with the character.
    """
    user_id: str
    display_name: str
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Chat:
    """Chat entity (ТЗ-002 punkt 4).

    Represents a conversation context (private chat, group, etc).
    """
    chat_id: str
    chat_type: str  # "private", "group", "supergroup"
    title: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ConversationMessage:
    """Single message in conversation history (ТЗ-002 punkt 20).

    Primary source of truth for all interactions.
    Memory pieces are derived from these messages.
    """
    message_id: str
    user_id: str
    chat_id: str
    channel: str  # "telegram", "desktop", "voice"
    timestamp: datetime
    role: str  # "user", "assistant", "system"
    content: str
    reply_to_message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WorkingMemoryItem:
    """Item in working memory (ТЗ-002 punkt 34).

    Represents promises, plans, pending questions, tasks.
    """
    id: str
    item_type: str  # "promise", "plan", "question", "task"
    content: str
    status: str = "active"  # "active", "completed", "cancelled"
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    due_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalContext:
    """Context for memory retrieval (ТЗ-002 punkt 27).

    Resolved from user request before retrieval.
    """
    # Identity
    user_id: str
    chat_id: str
    channel: str

    # Query
    query_text: str
    query_embedding: list[float]

    # Resolved access
    accessible_scopes: list[str]  # MemoryScope values
    is_desktop_owner: bool
    linked_user_ids: list[str]  # For cross-channel context

    # Metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
