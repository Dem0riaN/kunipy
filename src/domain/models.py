"""Domain models.

Domain models are independent of infrastructure and frameworks.
They represent core business concepts.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


@dataclass
class TelegramMessage:
    """Domain representation of Telegram message.

    Independent of TDLib wire format.
    """
    message_id: int
    chat_id: int
    user_id: int
    text: str
    timestamp: datetime

    # Optional fields
    media: Optional["MediaInfo"] = None
    reply_to: int | None = None
    edit_date: datetime | None = None
    is_outgoing: bool = False

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaInfo:
    """Media metadata extracted from Telegram message.

    Abstracts away TDLib-specific media types.
    """
    type: str  # "photo", "sticker", "video", "document", "voice", "animation"
    file_id: int
    mime_type: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None  # For video/voice

    # Sticker-specific
    emoji: str | None = None
    is_animated: bool = False
    is_video: bool = False

    # Document-specific
    filename: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    """Domain representation of user (across all channels)."""
    user_id: str
    display_name: str

    # Multi-channel identity (ТЗ-002 punkt 5)
    telegram_id: int | None = None
    desktop_owner: bool = False  # Is this the desktop owner?

    # Metadata
    first_seen: datetime | None = None
    last_interaction: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chat:
    """Domain representation of chat context."""
    chat_id: str
    chat_type: str  # "private", "group", "supergroup", "channel"
    title: str | None = None

    # Participants
    participant_ids: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Channel(Enum):
    """Communication channel (ТЗ-002 punkt 6)."""
    TELEGRAM = "telegram"
    DESKTOP = "desktop"
    VOICE = "voice"
    UNKNOWN = "unknown"


@dataclass
class Conversation:
    """Domain representation of conversation (chat + channel)."""
    user_id: str
    chat_id: str
    channel: Channel
    started_at: datetime
    last_message_at: datetime
    message_count: int = 0

    # Context
    metadata: dict[str, Any] = field(default_factory=dict)
