"""Anti-repeat detection service.

Detects repetitive bot responses using text similarity analysis.
Extracted from tools.py to maintain single responsibility principle.
"""

import difflib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AntiRepeatConfig:
    """Configuration for anti-repeat detection."""

    enabled: bool = True
    max_history: int = 5
    trigger_max: float = 0.85
    trigger_avg: float = 0.70


class AntiRepeatService:
    """Detects repetitive bot responses using difflib similarity."""

    def __init__(self, config: AntiRepeatConfig):
        """Initialize anti-repeat service.

        Args:
            config: Anti-repeat configuration
        """
        self._config = config

    def check_repetition(self, text: str, recent_bot_messages: list[str] | None) -> str | None:
        """Compare text against bot's recent messages and detect near-duplicates.

        Uses plain text similarity (difflib) rather than embeddings, trading a
        bit of semantic precision for zero extra network round-trips on every
        single message send.

        Args:
            text: Message text to check for repetition
            recent_bot_messages: List of bot's recent messages in this chat

        Returns:
            Rejection message with guidance if repetition detected, None otherwise
        """
        if not self._config.enabled:
            return None

        if not recent_bot_messages or not text.strip():
            return None

        history = recent_bot_messages[-self._config.max_history:]
        if not history:
            return None

        ratios = [
            difflib.SequenceMatcher(None, text, past).ratio()
            for past in history
            if past.strip()
        ]
        if not ratios:
            return None

        max_ratio = max(ratios)
        avg_ratio = sum(ratios) / len(ratios)

        if max_ratio >= self._config.trigger_max or avg_ratio >= self._config.trigger_avg:
            # Load anti_repeat prompt from prompts/anti_repeat.md
            try:
                from prompt_loader import load_anti_repeat_prompt
                anti_repeat_guidance = load_anti_repeat_prompt()
            except (ImportError, FileNotFoundError) as e:
                logger.warning(f"Failed to load anti_repeat prompt: {e}")
                anti_repeat_guidance = None

            base_error = (
                f"Error: this message is too similar to something you already said recently in this chat "
                f"(similarity={max_ratio:.2f})."
            )

            if anti_repeat_guidance:
                return f"{base_error}\n\n{anti_repeat_guidance}"
            else:
                return f"{base_error} Say something meaningfully different, or don't send anything."

        return None
