"""Thinking filter for hiding internal thoughts from LLM responses.

Implements filtering strategies to separate user-facing content from internal reasoning.
Following ТЗ-001 §32 - Character should not directly handle display logic.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import ClassVar

from .models import FilteredResponse

logger = logging.getLogger(__name__)


class FilterMode(Enum):
    """Thinking filter mode."""

    STRUCTURED = "structured"  # Expect JSON format
    HEURISTIC = "heuristic"  # Pattern-based detection
    OFF = "off"  # No filtering


class ThinkingFilter:
    """Filters internal thoughts from LLM responses.

    Supports multiple modes:
    - STRUCTURED: LLM returns JSON {"thinking": "...", "response": "..."}
    - HEURISTIC: Pattern-based detection and removal
    - OFF: No filtering (pass-through)

    Architecture: Strategy pattern for mode selection (ТЗ-001 §5)
    """

    THINKING_PATTERNS: ClassVar[list[str]] = [
        r"^Посмотрю.*$",
        r"^Интересно.*$",
        r"^Стоит проверить.*$",
        r"^Проверю.*$",
        r"^Вспомню.*$",
        r"^\[thinking\].*?\[/thinking\]",
    ]

    EMOTION_PATTERN: ClassVar[str] = r"emotion:\s*(\w+)"

    # Pattern to match emotion tags like [smirk], [anger], [happy], etc.
    EMOTION_TAG_PATTERN: ClassVar[str] = r"\[(smirk|anger|angry|happy|sad|curious|neutral|surprised|confused|excited|worried|thoughtful|frustrated|amused|serious|playful|confident|shy|proud|embarrassed|relieved|disappointed|impressed|skeptical|determined|calm|anxious|cheerful|melancholy|enthusiastic|cynical|hopeful|resigned|defiant|apologetic|grateful|envious|sympathetic|indifferent|bewildered|nostalgic|bitter|content|wistful)\]"

    def __init__(self, mode: FilterMode = FilterMode.STRUCTURED):
        """Initialize thinking filter.

        Args:
            mode: Filter mode to use (default: STRUCTURED)
        """
        self._mode = mode
        self._thinking_re = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.THINKING_PATTERNS
        ]
        self._emotion_re = re.compile(self.EMOTION_PATTERN, re.IGNORECASE)
        self._emotion_tag_re = re.compile(self.EMOTION_TAG_PATTERN, re.IGNORECASE)
        logger.info(f"ThinkingFilter initialized with mode: {mode.value}")

    def filter_response(self, content: str) -> FilteredResponse:
        """Filter complete response.

        Args:
            content: Raw LLM response

        Returns:
            FilteredResponse with separated content/thinking/emotion
        """
        if self._mode == FilterMode.OFF:
            return FilteredResponse(content=content, thinking=None, emotion=None)

        if self._mode == FilterMode.STRUCTURED:
            return self._filter_structured(content)

        return self._filter_heuristic(content)

    def _filter_structured(self, content: str) -> FilteredResponse:
        """Filter structured JSON response.

        Expected format:
        {
          "thinking": "Internal thoughts...",
          "emotion": "curious",
          "response": "User-facing message"
        }

        Args:
            content: JSON string (possibly wrapped in markdown code blocks)

        Returns:
            FilteredResponse with extracted fields
        """
        # Handle empty or whitespace-only content
        if not content or not content.strip():
            return FilteredResponse(content="", thinking=None, emotion=None)

        # Strip BOM and other invisible characters
        cleaned = content.strip()

        # Remove BOM (UTF-8, UTF-16, UTF-32)
        cleaned = cleaned.removeprefix('﻿')

        # Remove zero-width characters
        cleaned = cleaned.replace('\u200b', '')  # Zero-width space
        cleaned = cleaned.replace('‌', '')  # Zero-width non-joiner
        cleaned = cleaned.replace('‍', '')  # Zero-width joiner
        cleaned = cleaned.replace('﻿', '')  # Zero-width no-break space

        # Strip markdown code blocks if present (```json ... ``` or ``` ... ```)
        if cleaned.startswith("```"):
            # Remove opening ```json or ```
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned)

            # Extract response field
            response_text = data.get("response", "")

            # If response is empty or whitespace, log warning
            if not response_text or not response_text.strip():
                logger.warning("JSON response field is empty - LLM may have put content in thinking")
                # Try to salvage from thinking if response is truly empty
                thinking_text = data.get("thinking", "")
                if thinking_text and not response_text:
                    logger.warning("Using thinking field as response (fallback)")
                    response_text = thinking_text

            return FilteredResponse(
                content=response_text,
                thinking=data.get("thinking"),
                emotion=data.get("emotion"),
            )
        except (json.JSONDecodeError, AttributeError) as e:
            # Fallback to heuristic if JSON parsing fails
            logger.warning(f"Structured format expected but got non-JSON: {e}, falling back to heuristic")
            return self._filter_heuristic(content)

    def _filter_heuristic(self, content: str) -> FilteredResponse:
        """Filter using pattern matching.

        Removes lines matching thinking patterns and emotion tags.

        Args:
            content: Raw text content

        Returns:
            FilteredResponse with thinking and emotion tags stripped
        """
        # First, remove emotion tags like [smirk], [anger], etc.
        content_cleaned = self._emotion_tag_re.sub("", content)

        lines = content_cleaned.split("\n")
        filtered_lines = []
        thinking_lines = []
        emotion = None

        for line in lines:
            # Check for emotion tag (emotion: keyword format)
            emotion_match = self._emotion_re.search(line)
            if emotion_match:
                emotion = emotion_match.group(1)
                continue

            # Check for thinking patterns
            is_thinking = False
            for pattern in self._thinking_re:
                if pattern.match(line):
                    thinking_lines.append(line)
                    is_thinking = True
                    break

            if not is_thinking:
                filtered_lines.append(line)

        result_content = "\n".join(filtered_lines).strip()

        # Log if emotion tags were removed
        if self._emotion_tag_re.search(content):
            logger.debug("Removed emotion tags from heuristic response")

        return FilteredResponse(
            content=result_content,
            thinking="\n".join(thinking_lines) if thinking_lines else None,
            emotion=emotion,
        )
