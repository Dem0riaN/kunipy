"""Media processing service for voice, photo, sticker, and document messages.

This module handles:
- Transcription of voice messages
- Multimodal content creation for photos and stickers
- Text document extraction via MediaExtractorRegistry
"""

import logging

from ..config import Config
from ..domain.models import TelegramMessage
from ..interfaces.llm import IOpenAIChat
from ..interfaces.telegram import ITelegramClient
from .media.registry import MediaExtractorRegistry

logger = logging.getLogger(__name__)


class MediaService:
    """Service for processing multimedia content in Telegram messages.

    Responsibilities:
    - Transcribe voice messages to text
    - Create multimodal content (text + image) for vision-capable models
    - Extract content from documents via MediaExtractorRegistry
    - Handle download and processing errors gracefully
    """

    def __init__(
        self,
        telegram_client: ITelegramClient,
        openai_client: IOpenAIChat,
        config: Config,
        extractor_registry: MediaExtractorRegistry | None = None,
    ) -> None:
        """Initialize media service.

        Args:
            telegram_client: Client for downloading media files
            openai_client: Client for audio transcription and image description
            config: Application configuration (capabilities, endpoints)
            extractor_registry: Optional registry for document extractors
        """
        self._telegram = telegram_client
        self._openai = openai_client
        self._config = config
        self._extractor_registry = extractor_registry

    async def transcribe_voice_message(self, msg: TelegramMessage) -> str:
        """Download and transcribe a voice message.

        Returns empty string if:
        - Voice transcription is disabled/unconfigured
        - Download fails
        - Transcription fails

        Args:
            msg: Message containing voice media

        Returns:
            Transcribed text prefixed with "[voice message]", or empty string
        """
        if not msg.media:
            return ""

        # Check if hearing capability is enabled
        if not self._config.capability_hearing:
            logger.debug("Voice transcription disabled (capability_hearing=false)")
            return ""

        # Check if audio-to-text endpoint is configured
        if not self._config.llm_audio_to_text.endpoint.base_url:
            logger.debug("Voice transcription unconfigured (no llm_audio_to_text endpoint)")
            return ""

        file_id = msg.media.get("file_id")
        if not file_id:
            logger.warning("Voice message missing file_id")
            return ""

        try:
            # Download voice file
            audio_bytes = await self._telegram.download_file_bytes(file_id)
            if not audio_bytes:
                logger.warning(f"Failed to download voice file {file_id}")
                return ""

            # Transcribe (format="ogg" for Telegram voice messages)
            text = await self._openai.transcribe_audio(audio_bytes, format="ogg")
            if not text:
                return ""

            return f"[voice message] {text}"

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Voice transcription error: {e}")
            return ""

    async def get_image_bytes_and_mime(self, msg: TelegramMessage) -> tuple[bytes, str] | None:
        """Download image bytes from photo/sticker message.

        Handles WebP stickers by normalizing them to PNG/JPEG.

        Args:
            msg: Message containing photo or sticker media

        Returns:
            Tuple of (image_bytes, mime_type) or None if download fails
        """
        if not msg.media:
            return None

        file_id = msg.media.get("file_id")
        if not file_id:
            logger.warning(f"Media message missing file_id: {msg.media.get('type')}")
            return None

        try:
            # Download file
            image_bytes = await self._telegram.download_file_bytes(file_id)
            if not image_bytes:
                logger.warning(f"Failed to download media file {file_id}")
                return None

            # Determine MIME type
            media_type = msg.media.get("type")
            if media_type == "sticker":
                # Static stickers are typically WebP
                if not msg.media.get("is_animated") and not msg.media.get("is_video"):
                    mime_type = "image/webp"
                else:
                    # Animated/video stickers not supported yet
                    logger.debug("Animated/video sticker not supported for vision")
                    return None
            elif media_type == "photo":
                # Photos are typically JPEG
                mime_type = "image/jpeg"
            else:
                logger.warning(f"Unsupported media type for vision: {media_type}")
                return None

            return (image_bytes, mime_type)

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Image download error: {e}")
            return None

    async def read_text_document(self, msg: TelegramMessage) -> str:
        """Download and extract text document content.

        Uses MediaExtractorRegistry for extensible extraction.

        Returns empty string if:
        - Document processing is disabled
        - No extractor registry configured
        - Download fails
        - Extraction fails

        Args:
            msg: Message containing document media

        Returns:
            Formatted document content with header, or empty string
        """
        if not msg.media or msg.media.get("type") != "document":
            return ""

        # Check if document processing is enabled
        if not self._config.document_processing_enabled:
            logger.debug("Document processing disabled")
            return ""

        # Check if extractor registry is available
        if not self._extractor_registry:
            logger.warning("No extractor registry configured")
            return ""

        file_name = msg.media.get("file_name", "")
        mime_type = msg.media.get("mime_type")
        file_id = msg.media.get("file_id")

        if not file_id:
            logger.warning("Document message missing file_id")
            return ""

        # Extract extension from filename (case-insensitive)
        extension = None
        if file_name and "." in file_name:
            extension = "." + file_name.rsplit(".", 1)[-1].lower()

        try:
            # Download document
            doc_bytes = await self._telegram.download_file_bytes(file_id)
            if not doc_bytes:
                logger.warning(f"Failed to download document file {file_id}")
                return ""

            # Extract content using registry
            result = await self._extractor_registry.extract(
                data=doc_bytes,
                mime_type=mime_type,
                extension=extension,
                metadata={"filename": file_name}
            )

            if not result.success:
                # User-facing error message
                if result.error_message:
                    logger.info(f"Document extraction failed: {result.error_message}")
                    return f"[{result.error_message}]"
                return ""

            # Format with document header
            return f"[Document {file_name}]\n{result.content}"

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Document extraction error: {e}")
            return ""

    async def describe_photo_message(self, msg: TelegramMessage) -> str:
        """Download and describe a photo using vision model.

        LEGACY: This method uses the separate vision endpoint.
        Prefer creating multimodal content directly for vision-capable main models.

        Returns empty string if:
        - Vision capability is disabled/unconfigured
        - Download fails
        - Description fails

        Args:
            msg: Message containing photo media

        Returns:
            Photo description, or empty string
        """
        if not msg.media:
            return ""

        # Check if vision capability is enabled
        if not self._config.capability_vision:
            logger.debug("Photo description disabled (capability_vision=false)")
            return ""

        # Check if image-to-text endpoint is configured
        if not self._config.llm_image_to_text.endpoint.base_url:
            logger.debug("Photo description unconfigured (no llm_image_to_text endpoint)")
            return ""

        result = await self.get_image_bytes_and_mime(msg)
        if not result:
            return ""

        image_bytes, mime_type = result

        try:
            # Describe image using separate vision endpoint (legacy path)
            description = await self._openai.describe_image(
                image_bytes,
                mime_type=mime_type
            )
            return description or ""

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Photo description error: {e}")
            return ""
