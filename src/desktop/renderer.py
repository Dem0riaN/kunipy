"""OpenGL renderer stub (ТЗ-004)."""

import logging

logger = logging.getLogger(__name__)


class Renderer:
    """OpenGL renderer stub.

    When enabled=False, all methods are no-op.
    When enabled=True, will import OpenGL.
    """

    def __init__(self, config):
        """Initialize renderer stub."""
        self._config = config

    async def render(self) -> None:
        """Render frame (stub — no-op when disabled)."""
        if not self._config.enabled:
            return
        # TODO: Real implementation with OpenGL
        logger.debug("Renderer stub: render frame")

    async def init_context(self) -> None:
        """Initialize OpenGL context (stub)."""
        if not self._config.enabled:
            return
        logger.debug("Renderer stub: init context")

    async def destroy_context(self) -> None:
        """Destroy OpenGL context (stub)."""
        if not self._config.enabled:
            return
        logger.debug("Renderer stub: destroy context")
