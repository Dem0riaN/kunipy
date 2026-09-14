"""Desktop character stubs (ТЗ-004).

Provides safe stubs for desktop character (Live2D + PySide6) that do not
interfere with application operation when desktop_enabled = False (default).

Key principles:
- Bridges pattern: DesktopCharacter does NOT import memory/LLM directly
- Enabled flag: desktop_enabled = False → all methods no-op, zero heavy imports
- Graceful degradation: any desktop error = logged + ignored, main app continues
- Lazy imports: PySide6, cubism SDK, OpenGL imported only inside methods when enabled=True
"""

from .bridges import LLMBridge, MemoryBridge
from .character import DesktopCharacter
from .config import DesktopConfig

__all__ = [
    "DesktopCharacter",
    "DesktopConfig",
    "LLMBridge",
    "MemoryBridge",
]
