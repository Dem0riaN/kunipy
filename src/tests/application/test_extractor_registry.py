"""Tests for MediaExtractorRegistry.

Tests extractor registration and selection.
"""

import pytest

from src.application.media.extractor import ExtractionResult, MediaExtractor
from src.application.media.registry import MediaExtractorRegistry


class MockExtractor(MediaExtractor):
    """Mock extractor for testing."""

    def __init__(self, supported_extensions: list[str]):
        self.supported_extensions = supported_extensions
        self.extract_called = False

    def supports(self, mime_type, extension, metadata=None):
        return extension in self.supported_extensions

    async def extract(self, data, mime_type=None, extension=None, metadata=None):
        self.extract_called = True
        return ExtractionResult(
            success=True,
            content=f"Extracted by {self.__class__.__name__}",
            metadata={"extractor": self.__class__.__name__}
        )


@pytest.mark.asyncio
async def test_register_extractor():
    """Test extractor registration."""
    registry = MediaExtractorRegistry()
    extractor = MockExtractor([".txt"])

    registry.register(extractor)

    assert len(registry._extractors) == 1


@pytest.mark.asyncio
async def test_extract_with_matching_extractor():
    """Test extraction with matching extractor."""
    registry = MediaExtractorRegistry()
    extractor = MockExtractor([".txt"])
    registry.register(extractor)

    result = await registry.extract(b"test", extension=".txt")

    assert result.success
    assert extractor.extract_called
    assert "Extracted" in result.content


@pytest.mark.asyncio
async def test_extract_no_matching_extractor():
    """Test extraction with no matching extractor."""
    registry = MediaExtractorRegistry()
    extractor = MockExtractor([".txt"])
    registry.register(extractor)

    result = await registry.extract(b"test", extension=".pdf")

    assert not result.success
    assert "Unsupported" in result.error_message
    assert not extractor.extract_called


@pytest.mark.asyncio
async def test_multiple_extractors_first_match_wins():
    """Test first matching extractor is used."""
    registry = MediaExtractorRegistry()

    class FirstExtractor(MockExtractor):
        pass

    class SecondExtractor(MockExtractor):
        pass

    first = FirstExtractor([".txt"])
    second = SecondExtractor([".txt"])

    registry.register(first)
    registry.register(second)

    result = await registry.extract(b"test", extension=".txt")

    assert result.success
    assert first.extract_called
    assert not second.extract_called


@pytest.mark.asyncio
async def test_extension_case_normalization():
    """Test extension is normalized to lowercase."""
    registry = MediaExtractorRegistry()
    extractor = MockExtractor([".txt"])
    registry.register(extractor)

    # Registry normalizes to lowercase before calling supports()
    result = await registry.extract(b"test", extension=".TXT")

    assert result.success
    assert extractor.extract_called


@pytest.mark.asyncio
async def test_extractor_exception_handling():
    """Test exception from extractor is handled gracefully."""
    registry = MediaExtractorRegistry()

    class FailingExtractor(MediaExtractor):
        def supports(self, mime_type, extension, metadata=None):
            return extension == ".txt"

        async def extract(self, data, mime_type=None, extension=None, metadata=None):
            raise RuntimeError("Extraction failed")

    registry.register(FailingExtractor())

    result = await registry.extract(b"test", extension=".txt")

    assert not result.success
    assert "failed" in result.error_message.lower()
