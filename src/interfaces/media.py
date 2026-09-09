"""Media and vision interface protocols (ТЗ-003 foundation)."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class MediaType(Enum):
    """Media type classification."""
    PHOTO = "photo"
    STICKER = "sticker"
    STICKER_ANIMATED = "sticker_animated"
    STICKER_VIDEO = "sticker_video"
    ANIMATION = "animation"  # GIF
    VIDEO = "video"
    VIDEO_NOTE = "video_note"  # Round video message
    DOCUMENT = "document"
    VOICE = "voice"
    AUDIO = "audio"


@dataclass
class ProcessedMedia:
    """Processed media ready for vision model.

    Result of media processing (e.g., WebP→PNG conversion).
    """
    media_type: MediaType
    data: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None
    metadata: dict | None = None


class IMediaHandler(Protocol):
    """Protocol for media processing (ТЗ-003).

    Handles format conversion and normalization for vision models.
    Implementation deferred to Phase 3.
    """

    async def process_image(
        self,
        image_data: bytes,
        mime_type: str
    ) -> ProcessedMedia:
        """Process image for vision model.

        Handles format conversion if needed.

        Args:
            image_data: Raw image bytes
            mime_type: Original MIME type

        Returns:
            Processed media
        """
        ...

    async def process_sticker(
        self,
        sticker_data: bytes,
        mime_type: str,
        is_animated: bool = False,
        is_video: bool = False
    ) -> ProcessedMedia:
        """Process sticker for vision model.

        Implements ТЗ-003: WebP→PNG conversion for static stickers.

        Args:
            sticker_data: Raw sticker bytes
            mime_type: Original MIME type (often "image/webp")
            is_animated: Whether sticker is animated
            is_video: Whether sticker is video

        Returns:
            Processed media (PNG for static, original for animated)
        """
        ...

    async def process_document(
        self,
        document_data: bytes,
        mime_type: str,
        filename: str | None = None
    ) -> str | None:
        """Process document (text extraction for .txt/.md).

        Implements ТЗ-003: text document content extraction.

        Args:
            document_data: Raw document bytes
            mime_type: Document MIME type
            filename: Original filename

        Returns:
            Extracted text if supported, None otherwise
        """
        ...

    async def extract_video_frame(
        self,
        video_data: bytes,
        timestamp_seconds: float = 0.0
    ) -> ProcessedMedia | None:
        """Extract frame from video.

        Deferred to later phase (ТЗ-003 notes this is not yet implemented).

        Args:
            video_data: Raw video bytes
            timestamp_seconds: Frame timestamp

        Returns:
            Extracted frame as image, None if not supported
        """
        ...


class IVisionService(Protocol):
    """Protocol for vision capabilities (ТЗ-003).

    Handles multimodal LLM interaction with images.
    Implementation deferred to Phase 3.
    """

    async def describe_image(
        self,
        image_data: bytes,
        prompt: str,
        mime_type: str = "image/jpeg"
    ) -> str:
        """Get text description of image.

        Fallback for text-only models.

        Args:
            image_data: Image bytes
            prompt: Vision prompt
            mime_type: Image MIME type

        Returns:
            Text description
        """
        ...

    async def create_multimodal_message(
        self,
        text: str,
        images: list[bytes],
        mime_types: list[str] | None = None
    ) -> "Message":  # noqa: F821
        """Create message with text + images.

        Implements ТЗ-003: multimodal content for vision models.

        Creates OpenAI-compatible message:
        {
          "role": "user",
          "content": [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:..."}}
          ]
        }

        Args:
            text: Message text
            images: List of image bytes
            mime_types: MIME types for each image

        Returns:
            Message with multimodal content
        """
        ...

    async def supports_vision(self, model: str) -> bool:
        """Check if model supports vision.

        Args:
            model: Model identifier

        Returns:
            True if model has vision capabilities
        """
        ...
