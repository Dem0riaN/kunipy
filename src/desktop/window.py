"""Window management stub (ТЗ-004)."""

import logging

logger = logging.getLogger(__name__)


class WindowManager:
    """Window management stub.

    When enabled=False, all methods are no-op.
    When enabled=True, will import PySide6 and create real window.
    """

    def __init__(self, config):
        """Initialize window manager stub."""
        self._config = config
        self._window = None

    async def create_window(self, width: int, height: int) -> None:
        """Create window (stub — no-op when disabled)."""
        if not self._config.enabled:
            return
        # TODO: Real implementation with PySide6
        logger.debug(f"Window stub: create {width}x{height}")

    async def destroy_window(self) -> None:
        """Destroy window (stub — no-op when disabled)."""
        if not self._config.enabled:
            return
        # TODO: Real implementation
        logger.debug("Window stub: destroy")

    async def is_open(self) -> bool:
        """Check if window is open."""
        return self._config.enabled and self._window is not None
