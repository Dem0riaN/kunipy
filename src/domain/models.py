"""Domain models.

Domain models are independent of infrastructure and frameworks.
They represent core business concepts.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


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
    reply_to: Optional[int] = None
    edit_date: Optional[datetime] = None
    is_outgoing: bool = False

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaInfo:
    """Media metadata extracted from Telegram message.

    Abstracts away TDLib-specific media types.
    """
    type: str  # "photo", "sticker", "video", "document", "voice", "animation"
    file_id: int
    mime_type: Optional[str] = None
    size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None  # For video/voice

    # Sticker-specific
    emoji: Optional[str] = None
    is_animated: bool = False
    is_video: bool = False

    # Document-specific
    filename: Optional[str] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    """Domain representation of user (across all channels)."""
    user_id: str
    display_name: str

    # Multi-channel identity (ТЗ-002 punkt 5)
    telegram_id: Optional[int] = None
    desktop_owner: bool = False  # Is this the desktop owner?

    # Metadata
    first_seen: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chat:
    """Domain representation of chat context."""
    chat_id: str
    chat_type: str  # "private", "group", "supergroup", "channel"
    title: Optional[str] = None

    # Participants
    participant_ids: List[str] = field(default_factory=list)

    # Metadata
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


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
    metadata: Dict[str, Any] = field(default_factory=dict)
