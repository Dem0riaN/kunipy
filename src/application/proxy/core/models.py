"""Domain models for proxy core.

Typed models following ТЗ-001 §10.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionState(Enum):
    """Session processing state."""

    IDLE = "idle"
    PROCESSING = "processing"
    INTERRUPTED = "interrupted"


@dataclass
class FilteredResponse:
    """Filtered LLM response (domain model).

    Separates user-facing content from internal thinking.
    """

    content: str  # Clean response for user
    thinking: str | None  # Extracted thinking (hidden)
    emotion: str | None  # Extracted emotion


@dataclass
class UserContext:
    """User context for proxy session (domain model).

    Tracks user identity and cross-channel memory linking.
    Following ТЗ-001 §23 - Working Memory integration.
    """

    user_id: str
    is_papik: bool
    telegram_id: str | None
    linked_user_ids: list[str]  # For cross-channel memory (Telegram ↔ Proxy)
    working_memory: str
    display_name: str
