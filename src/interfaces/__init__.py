"""Protocol definitions for all major components.

This module defines interfaces using Python's typing.Protocol for structural subtyping.
All dependencies between layers should go through these protocols.
"""

from .delivery import DeliveryState, IMessageDeliveryTracker
from .llm import IEmbeddingProvider, IOpenAIChat
from .memory import IMemoryStore, IWorkingMemory, MemoryKind, MemoryScope
from .telegram import ITelegramClient, ITelegramMessageService
from .worker import INotificationManager

__all__ = [
    "DeliveryState",
    "IEmbeddingProvider",
    "IMemoryStore",
    "IMessageDeliveryTracker",
    "INotificationManager",
    "IOpenAIChat",
    "ITelegramClient",
    "ITelegramMessageService",
    "IWorkingMemory",
    "MemoryKind",
    "MemoryScope",
]
