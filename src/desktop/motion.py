"""Motion controller stub (ТЗ-004)."""

import logging

logger = logging.getLogger(__name__)


class MotionController:
    """Motion controller stub.

    When enabled=False, all methods are no-op.
    """

    def __init__(self, config):
        """Initialize motion controller stub."""
        self._config = config
        self._current_motion = None
        self._playing = False

    async def play_motion(self, motion_name: str) -> None:
        """Play motion (stub — no-op when disabled)."""
        if not self._config.enabled:
            return
        self._current_motion = motion_name
        self._playing = True
        logger.debug(f"Motion stub: play {motion_name}")

    async def stop_motion(self) -> None:
        """Stop motion (stub)."""
        if not self._config.enabled:
            return
        self._playing = False
        logger.debug("Motion stub: stop")

    async def is_playing(self) -> bool:
        """Check if motion is playing."""
        return self._config.enabled and self._playing
