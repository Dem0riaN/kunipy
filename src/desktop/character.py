"""Desktop character stub (ТЗ-004).

Main character class. When enabled=False (default), all methods are no-op
and no heavy dependencies (PySide6, Live2D, OpenGL) are imported.

Bridges pattern: DesktopCharacter accepts MemoryBridge and LLMBridge via
constructor injection. Desktop package does NOT import memory/LLM modules.
"""

import logging
from typing import TYPE_CHECKING

from .bridges import LLMBridge, MemoryBridge, NoOpLLMBridge, NoOpMemoryBridge
from .config import DesktopConfig

if TYPE_CHECKING:
    from .interfaces import ICharacterState

logger = logging.getLogger(__name__)


class DesktopCharacter:
    """Desktop character stub.

    When enabled=False (default):
    - All methods return immediately (no-op)
    - No heavy imports (PySide6, Live2D, OpenGL)
    - No resources allocated

    When enabled=True:
    - Imports heavy dependencies lazily inside methods
    - Any error is logged and ignored (graceful degradation)
    """

    def __init__(
        self,
        config: DesktopConfig,
        memory_bridge: MemoryBridge | None = None,
        llm_bridge: LLMBridge | None = None,
    ):
        """Initialize desktop character.

        Args:
            config: Desktop configuration
            memory_bridge: Memory bridge (injected, not imported)
            llm_bridge: LLM bridge (injected, not imported)
        """
        self._config = config
        self._memory = memory_bridge or NoOpMemoryBridge()
        self._llm = llm_bridge or NoOpLLMBridge()
        self._running = False

    async def start(self) -> None:
        """Start desktop character.

        If enabled=False, returns immediately.
        If enabled=True, imports heavy dependencies and initializes.
        """
        if not self._config.enabled:
            logger.info("Desktop disabled (enabled=False), skipping startup")
            return

        try:
            # Lazy import heavy dependencies only when enabled
            logger.info("Desktop enabled, initializing (stub — real implementation in Phase D.2)")
            # TODO: Real implementation will import PySide6, Live2D, OpenGL here
            # from .window import WindowManager
            # from .model import ModelLoader
            # from .renderer import Renderer
            self._running = True
            logger.info("Desktop character started (stub mode)")
        except ImportError as e:
            logger.warning(f"Desktop dependencies not installed: {e}")
            self._running = False
        except Exception as e:
            logger.exception(f"Desktop startup failed: {e}")
            self._running = False

    async def stop(self) -> None:
        """Stop desktop character.

        If enabled=False, returns immediately.
        If enabled=True, cleans up resources.
        """
        if not self._config.enabled:
            return

        try:
            logger.info("Stopping desktop character")
            # TODO: Real implementation will clean up PySide6, Live2D, OpenGL resources
            self._running = False
            logger.info("Desktop character stopped")
        except Exception as e:
            logger.exception(f"Desktop shutdown failed (ignored): {e}")
            self._running = False

    def is_running(self) -> bool:
        """Check if desktop character is running."""
        return self._running

    def get_state(self) -> "ICharacterState | None":
        """Get character state (stub — returns None when not running)."""
        # TODO: Real implementation will return actual state object
        return None
