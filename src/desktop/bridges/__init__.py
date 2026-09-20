"""Bridges for desktop integration (ТЗ-004).

Bridges decouple desktop from memory/LLM subsystems. Real bridges will
wrap Diary/MemoryService — desktop package itself knows nothing about them.
"""

from .llm_bridge import LLMBridge, NoOpLLMBridge
from .memory_bridge import MemoryBridge, NoOpMemoryBridge

__all__ = [
    "LLMBridge",
    "MemoryBridge",
    "NoOpLLMBridge",
    "NoOpMemoryBridge",
]
