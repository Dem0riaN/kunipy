"""Media extractor base abstraction.

Provides interface for extracting content from various media types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractionResult:
    """Result of media extraction.

    Attributes:
        success: Whether extraction succeeded
        content: Extracted text content (empty if failed)
        error_message: User-facing error message (if failed)
        metadata: Additional metadata about extraction
    """
    success: bool
    content: str
    error_message: str = ""
    metadata: dict[str, Any] | None = None


class MediaExtractor(ABC):
    """Base class for media content extractors.

    Responsibilities:
    - Determine if media type is supported
    - Extract content from raw bytes
    - Return normalized result

    Does NOT handle:
    - Telegram/TDLib interaction
    - File downloading
    - Character context
    - LLM integration
    """

    @abstractmethod
    def supports(
        self,
        mime_type: str | None,
        extension: str | None,
        metadata: dict[str, Any] | None = None
    ) -> bool:
        """Check if this extractor supports the given media.

        Args:
            mime_type: MIME type (e.g. "text/plain")
            extension: File extension (e.g. ".txt")
            metadata: Additional metadata

        Returns:
            True if this extractor can process the media
        """
        pass

    @abstractmethod
    async def extract(
        self,
        data: bytes,
        mime_type: str | None = None,
        extension: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> ExtractionResult:
        """Extract content from media bytes.

        Args:
            data: Raw media bytes
            mime_type: MIME type hint
            extension: File extension hint
            metadata: Additional metadata

        Returns:
            ExtractionResult with content or error
        """
        pass
