"""Media processing service for voice and photo messages.

This module handles transcription of voice messages and description of photos
using configured LLM endpoints (audio-to-text and vision).
"""

import logging

from ..config import Config
from ..domain.models import TelegramMessage
from ..interfaces.llm import IOpenAIChat
from ..interfaces.telegram import ITelegramClient

logger = logging.getLogger(__name__)


class MediaService:
    """Service for processing multimedia content in Telegram messages.

    Responsibilities:
    - Transcribe voice messages to text
    - Describe photos using vision models
    - Handle download and processing errors gracefully
    """

    def __init__(
        self,
        telegram_client: ITelegramClient,
        openai_client: IOpenAIChat,
        config: Config,
    ) -> None:
        """Initialize media service.

        Args:
            telegram_client: Client for downloading media files
            openai_client: Client for audio transcription and image description
            config: Application configuration (capabilities, endpoints)
        """
        self._telegram = telegram_client
        self._openai = openai_client
        self._config = config

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

    async def describe_photo_message(self, msg: TelegramMessage) -> str:
        """Download and describe a photo using vision model.

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

        file_id = msg.media.get("file_id")
        if not file_id:
            logger.warning("Photo message missing file_id")
            return ""

        try:
            # Download photo
            image_bytes = await self._telegram.download_file_bytes(file_id)
            if not image_bytes:
                logger.warning(f"Failed to download photo file {file_id}")
                return ""

            # Describe image
            description = await self._openai.describe_image(
                image_bytes,
                mime_type="image/jpeg"
            )
            return description or ""

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Photo description error: {e}")
            return ""
