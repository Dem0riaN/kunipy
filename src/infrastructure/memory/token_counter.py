"""Token counting utilities with tiktoken fallback (Phase 3).

Counts tokens for messages and text to determine when context exceeds thresholds.
Uses tiktoken when available, falls back to len(text)//4 estimation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import tiktoken, fall back to estimation
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.info("tiktoken not available, using len(text)//4 estimation")


class TokenCounter:
    """Token counter with tiktoken backend and fallback estimation.

    Uses tiktoken for accurate counting when available.
    Falls back to len(text)//4 (~4 chars per token) when tiktoken unavailable.
    """

    def __init__(self, model: str = "gpt-4"):
        """Initialize token counter.

        Args:
            model: Model name for tiktoken encoding selection
        """
        self._model = model
        self._encoder: Any = None

        if _TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.encoding_for_model(model)
                logger.debug(f"Loaded tiktoken encoding for {model}")
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to load tiktoken for {model}, using fallback: {e}")
                self._encoder = None

    def count_text(self, text: str) -> int:
        """Count tokens in text string.

        Args:
            text: Input text to count

        Returns:
            Token count (accurate if tiktoken available, else estimated)
        """
        if not text:
            return 0

        if self._encoder:
            return len(self._encoder.encode(text))
        else:
            # Fallback: ~4 chars per token
            return len(text) // 4

    def count_messages(self, messages: list[Any]) -> int:
        """Count tokens across list of messages.

        Args:
            messages: List of Message objects or dicts with 'content' field

        Returns:
            Total token count across all messages
        """
        total = 0
        for msg in messages:
            content = self._extract_content(msg)
            if content:
                total += self.count_text(content)
            # Add overhead for message structure (role, delimiters)
            total += 4
        return total

    def _extract_content(self, msg: Any) -> str:
        """Extract text content from message object.

        Handles both Message dataclass and dict formats.

        Args:
            msg: Message object or dict

        Returns:
            Extracted text content
        """
        if isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = getattr(msg, "content", "")

        # Handle multimodal content (list of dicts with text/image)
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            return " ".join(text_parts)

        return str(content) if content else ""

    @property
    def is_accurate(self) -> bool:
        """Check if using accurate tiktoken counting.

        Returns:
            True if tiktoken available, False if using estimation
        """
        return self._encoder is not None
