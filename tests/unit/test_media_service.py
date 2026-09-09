"""Unit tests for MediaService.

Tests voice transcription and photo description functionality.
Part of ТЗ-001 Phase 1 validation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from pathlib import Path

from src.application.media_service import MediaService
from src.domain.models import TelegramMessage
from src.config import Config, Endpoint, EndpointAndModel


@pytest.fixture
def test_config():
    """Create test configuration."""
    config = Config()

    # Audio config
    config.capability_hearing = True
    config.llm_audio_to_text = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:9000/v1/"),
        model="whisper-base"
    )

    # Vision config
    config.capability_vision = True
    config.llm_image_to_text = EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="llava"
    )

    return config


@pytest.fixture
def mock_telegram_client():
    """Create mock Telegram client."""
    client = AsyncMock()
    client.download_file_bytes = AsyncMock()
    return client


@pytest.fixture
def mock_openai_client():
    """Create mock OpenAI client."""
    client = AsyncMock()
    client.transcribe_audio = AsyncMock()
    client.describe_image = AsyncMock()
    return client


@pytest.fixture
def media_service(mock_telegram_client, mock_openai_client, test_config):
    """Create MediaService with mocks."""
    return MediaService(
        telegram_client=mock_telegram_client,
        openai_client=mock_openai_client,
        config=test_config
    )


@pytest.mark.asyncio
async def test_transcribe_voice_success(media_service, mock_telegram_client, mock_openai_client):
    """Test successful voice message transcription."""
    # Setup
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice", "file_id": "voice123"}
    )

    mock_telegram_client.download_file_bytes.return_value = b"audio_data"
    mock_openai_client.transcribe_audio.return_value = "Hello world"

    # Execute
    result = await media_service.transcribe_voice_message(msg)

    # Verify
    assert result == "[voice message] Hello world"
    mock_telegram_client.download_file_bytes.assert_called_once_with("voice123")
    mock_openai_client.transcribe_audio.assert_called_once_with(b"audio_data", format="ogg")


@pytest.mark.asyncio
async def test_transcribe_voice_disabled(media_service, test_config):
    """Test voice transcription when capability is disabled."""
    test_config.capability_hearing = False

    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice", "file_id": "voice123"}
    )

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_no_endpoint(media_service, test_config):
    """Test voice transcription when endpoint not configured."""
    test_config.llm_audio_to_text.endpoint.base_url = ""

    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice", "file_id": "voice123"}
    )

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_no_media(media_service):
    """Test voice transcription with no media."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="text message"
    )

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_missing_file_id(media_service):
    """Test voice transcription with missing file_id."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice"}  # No file_id
    )

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_download_fails(media_service, mock_telegram_client):
    """Test voice transcription when download fails."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice", "file_id": "voice123"}
    )

    mock_telegram_client.download_file_bytes.return_value = None

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_transcription_fails(media_service, mock_telegram_client, mock_openai_client):
    """Test voice transcription when transcription fails."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "voice", "file_id": "voice123"}
    )

    mock_telegram_client.download_file_bytes.return_value = b"audio_data"
    mock_openai_client.transcribe_audio.side_effect = Exception("API error")

    result = await media_service.transcribe_voice_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_describe_photo_success(media_service, mock_telegram_client, mock_openai_client):
    """Test successful photo description."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "photo", "file_id": "photo123"}
    )

    mock_telegram_client.download_file_bytes.return_value = b"image_data"
    mock_openai_client.describe_image.return_value = "A beautiful sunset"

    result = await media_service.describe_photo_message(msg)

    assert result == "A beautiful sunset"
    mock_telegram_client.download_file_bytes.assert_called_once_with("photo123")
    mock_openai_client.describe_image.assert_called_once_with(
        b"image_data",
        mime_type="image/jpeg"
    )


@pytest.mark.asyncio
async def test_describe_photo_disabled(media_service, test_config):
    """Test photo description when capability is disabled."""
    test_config.capability_vision = False

    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "photo", "file_id": "photo123"}
    )

    result = await media_service.describe_photo_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_describe_photo_no_endpoint(media_service, test_config):
    """Test photo description when endpoint not configured."""
    test_config.llm_image_to_text.endpoint.base_url = ""

    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "photo", "file_id": "photo123"}
    )

    result = await media_service.describe_photo_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_describe_photo_no_media(media_service):
    """Test photo description with no media."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="text message"
    )

    result = await media_service.describe_photo_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_describe_photo_download_fails(media_service, mock_telegram_client):
    """Test photo description when download fails."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "photo", "file_id": "photo123"}
    )

    mock_telegram_client.download_file_bytes.return_value = None

    result = await media_service.describe_photo_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_describe_photo_description_fails(media_service, mock_telegram_client, mock_openai_client):
    """Test photo description when API fails."""
    msg = TelegramMessage(
        id=1,
        chat_id=123,
        sender_id=456,
        date=1234567890,
        content="",
        media={"type": "photo", "file_id": "photo123"}
    )

    mock_telegram_client.download_file_bytes.return_value = b"image_data"
    mock_openai_client.describe_image.side_effect = Exception("Vision API error")

    result = await media_service.describe_photo_message(msg)

    assert result == ""


@pytest.mark.asyncio
async def test_media_service_initialization(mock_telegram_client, mock_openai_client, test_config):
    """Test MediaService initialization."""
    service = MediaService(
        telegram_client=mock_telegram_client,
        openai_client=mock_openai_client,
        config=test_config
    )

    assert service._telegram is mock_telegram_client
    assert service._openai is mock_openai_client
    assert service._config is test_config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
