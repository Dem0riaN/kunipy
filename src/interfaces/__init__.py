"""Protocol definitions for all major components.

This module defines interfaces using Python's typing.Protocol for structural subtyping.
All dependencies between layers should go through these protocols.
"""

from .llm import IOpenAIChat, IEmbeddingProvider
from .telegram import ITelegramClient, ITelegramMessageService
from .memory import IMemoryStore, IWorkingMemory, MemoryScope, MemoryKind
from .delivery import IMessageDeliveryTracker, DeliveryState
from .worker import INotificationManager

__all__ = [
    # LLM
    "IOpenAIChat",
    "IEmbeddingProvider",
    # Telegram
    "ITelegramClient",
    "ITelegramMessageService",
    # Memory
    "IMemoryStore",
    "IWorkingMemory",
    "MemoryScope",
    "MemoryKind",
    # Delivery
    "IMessageDeliveryTracker",
    "DeliveryState",
    # Worker
    "INotificationManager",
]
