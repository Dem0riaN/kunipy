"""Live2D model loader stub (ТЗ-004)."""

import logging

logger = logging.getLogger(__name__)


class ModelLoader:
    """Live2D model loader stub.

    When enabled=False, all methods are no-op.
    When enabled=True, will import cubism SDK.
    """

    def __init__(self, config):
        """Initialize model loader stub."""
        self._config = config
        self._model = None

    async def load(self, model_path: str) -> bool:
        """Load Live2D model (stub — returns False when disabled)."""
        if not self._config.enabled:
            return False
        # TODO: Real implementation with cubism SDK
        logger.debug(f"Model stub: load {model_path}")
        return True

    async def unload(self) -> None:
        """Unload model (stub)."""
        if not self._config.enabled:
            return
        self._model = None
        logger.debug("Model stub: unload")

    async def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._config.enabled and self._model is not None
