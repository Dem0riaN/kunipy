"""Environment rendering stub (ТЗ-004)."""

import logging

logger = logging.getLogger(__name__)


class EnvironmentRenderer:
    """Environment rendering stub.

    When enabled=False, all methods are no-op.
    """

    def __init__(self, config):
        """Initialize environment renderer stub."""
        self._config = config
        self._current_scene = None

    async def render(self) -> None:
        """Render environment (stub — no-op when disabled)."""
        if not self._config.enabled:
            return
        # TODO: Real implementation
        logger.debug("Environment stub: render")

    async def load_scene(self, scene_name: str) -> None:
        """Load scene (stub)."""
        if not self._config.enabled:
            return
        self._current_scene = scene_name
        logger.debug(f"Environment stub: load scene {scene_name}")
