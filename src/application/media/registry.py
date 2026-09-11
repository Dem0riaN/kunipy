"""Media extractor registry.

Manages registration and selection of media extractors.
"""

import logging
from typing import Any

from .extractor import ExtractionResult, MediaExtractor

logger = logging.getLogger(__name__)


class MediaExtractorRegistry:
    """Registry for media extractors.

    Responsibilities:
    - Register extractors
    - Select appropriate extractor for media
    - Execute extraction

    Uses simple strategy pattern - no complex plugin system.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._extractors: list[MediaExtractor] = []

    def register(self, extractor: MediaExtractor) -> None:
        """Register a media extractor.

        Args:
            extractor: Extractor instance to register
        """
        self._extractors.append(extractor)
        logger.debug(f"Registered extractor: {type(extractor).__name__}")

    async def extract(
        self,
        data: bytes,
        mime_type: str | None = None,
        extension: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> ExtractionResult:
        """Extract content using appropriate extractor.

        Iterates through registered extractors in order until one supports the media.

        Args:
            data: Raw media bytes
            mime_type: MIME type hint
            extension: File extension hint
            metadata: Additional metadata

        Returns:
            ExtractionResult (success=False if no extractor found)
        """
        # Normalize extension to lowercase for case-insensitive matching
        norm_extension = extension.lower() if extension else None

        # Find first supporting extractor
        for extractor in self._extractors:
            if extractor.supports(mime_type, norm_extension, metadata):
                logger.debug(
                    f"Using {type(extractor).__name__} for "
                    f"mime={mime_type} ext={norm_extension}"
                )
                try:
                    return await extractor.extract(data, mime_type, norm_extension, metadata)
                except Exception as e:  # noqa: BLE001
                    # Broad exception catch is intentional - we don't want one extractor's failure
                    # to crash the entire extraction pipeline
                    logger.error(f"Extractor {type(extractor).__name__} failed: {e}")
                    return ExtractionResult(
                        success=False,
                        content="",
                        error_message=f"Extraction failed: {e}"
                    )

        # No extractor found
        logger.debug(f"No extractor found for mime={mime_type} ext={norm_extension}")
        return ExtractionResult(
            success=False,
            content="",
            error_message="Unsupported file type"
        )
