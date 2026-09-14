"""Text document extractor.

Supports .txt files with multiple encodings.
"""

import logging
from typing import Any

from .extractor import ExtractionResult, MediaExtractor

logger = logging.getLogger(__name__)

# Encoding detection order
# Note: utf-8 before utf-8-sig so we can distinguish files with/without BOM
ENCODINGS = [
    "utf-8",      # UTF-8 without BOM (strict)
    "utf-8-sig",  # UTF-8 with BOM
    "utf-16",     # UTF-16 (with BOM detection)
    "cp1251",     # Windows Cyrillic
]


class TxtExtractor(MediaExtractor):
    """Extractor for plain text documents.

    Supports:
    - UTF-8
    - UTF-8 with BOM
    - UTF-16 (LE/BE with BOM)
    - CP1251 (Windows Cyrillic)

    Configuration:
    - max_size_bytes: Maximum file size to process
    - max_context_chars: Maximum characters to include in LLM context
    """

    def __init__(
        self,
        max_size_bytes: int = 1024 * 1024,  # 1MB default
        max_context_chars: int = 50000       # ~12.5k tokens default
    ) -> None:
        """Initialize text extractor.

        Args:
            max_size_bytes: Maximum physical file size
            max_context_chars: Maximum characters for LLM context
        """
        self.max_size_bytes = max_size_bytes
        self.max_context_chars = max_context_chars

    def supports(
        self,
        mime_type: str | None,
        extension: str | None,
        metadata: dict[str, Any] | None = None
    ) -> bool:
        """Check if this is a text file.

        Args:
            mime_type: MIME type
            extension: File extension (normalized to lowercase by registry)
            metadata: Additional metadata

        Returns:
            True if text/plain or .txt extension
        """
        # Check MIME type
        if mime_type and mime_type.lower() == "text/plain":
            return True

        # Check extension (normalize to lowercase for case-insensitive matching)
        return bool(extension and extension.lower() == ".txt")

    async def extract(
        self,
        data: bytes,
        mime_type: str | None = None,
        extension: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> ExtractionResult:
        """Extract text content.

        Args:
            data: Raw file bytes
            mime_type: MIME type hint
            extension: File extension hint
            metadata: Additional metadata (may contain filename)

        Returns:
            ExtractionResult with decoded text or error
        """
        filename = (metadata or {}).get("filename", "document.txt")

        # Check physical size limit
        if len(data) > self.max_size_bytes:
            size_mb = len(data) / (1024 * 1024)
            return ExtractionResult(
                success=False,
                content="",
                error_message=f"File {filename} is too large ({size_mb:.1f}MB). Maximum size: {self.max_size_bytes / (1024 * 1024):.1f}MB"
            )

        # Check if empty
        if not data:
            return ExtractionResult(
                success=False,
                content="",
                error_message=f"File {filename} is empty"
            )

        # Try to decode with supported encodings
        text = None
        used_encoding = None

        for encoding in ENCODINGS:
            try:
                text = data.decode(encoding)
                used_encoding = encoding
                break
            except (UnicodeDecodeError, LookupError):
                continue

        # If all encodings failed
        if text is None:
            return ExtractionResult(
                success=False,
                content="",
                error_message=f"Could not decode {filename}. Supported encodings: UTF-8, UTF-16, CP1251"
            )

        # Normalize line endings to \n
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Check context budget
        original_length = len(text)
        truncated = False
        if len(text) > self.max_context_chars:
            text = text[:self.max_context_chars]
            truncation_msg = f"\n\n[... truncated, showing first {self.max_context_chars} of {original_length} characters]"
            text = text + truncation_msg
            truncated = True
            logger.info(
                f"Truncated {filename} from {original_length} to {self.max_context_chars} chars"
            )

        return ExtractionResult(
            success=True,
            content=text,
            metadata={
                "encoding": used_encoding,
                "original_size": len(data),
                "decoded_length": original_length,
                "truncated": truncated
            }
        )
