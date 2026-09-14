"""LLM bridge interface (ТЗ-004).

Contract for desktop ↔ LLM integration. Desktop package depends on
this Protocol, not on concrete OpenAIChat implementations.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBridge(Protocol):
    """Interface for LLM operations from desktop."""

    async def generate_response(self, message: str) -> str:
        """Generate LLM response for user message.

        Args:
            message: User message text

        Returns:
            Generated response text
        """
        ...

    async def on_message_sent(self, message: str) -> None:
        """Notify bridge that a message was sent (for animations, lip sync, etc).

        Args:
            message: The message text
        """
        ...


class NoOpLLMBridge:
    """No-op stub: returns empty strings, does nothing."""

    async def generate_response(self, message: str) -> str:
        """Return empty string (no response)."""
        return ""

    async def on_message_sent(self, message: str) -> None:
        """Do nothing."""
