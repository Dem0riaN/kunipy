"""LLM interface protocols."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Message:
    """LLM message (user, assistant, system, tool)."""
    role: str
    content: str | list[dict[str, Any]] = ""
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass
class Response:
    """LLM response."""
    content: str
    model: str
    finish_reason: str
    usage: dict[str, int] | None = None
    tool_calls: list[dict[str, Any]] | None = None


class IOpenAIChat(Protocol):
    """Protocol for LLM chat interface.

    Implementations: OpenAIChat (src/openai_chat.py)
    """

    async def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs
    ) -> Response:
        """Send chat request to LLM.

        Args:
            messages: Conversation history
            model: Model name override
            tools: Available tool definitions
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response
            **kwargs: Additional provider-specific parameters

        Returns:
            Response with content and metadata
        """
        ...

    async def chat_stream(
        self,
        messages: list[Message],
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream chat response.

        Yields:
            Response chunks as they arrive
        """
        ...

    async def embedding(
        self,
        text: str,
        model: str | None = None
    ) -> list[float]:
        """Generate embedding vector.

        Args:
            text: Input text
            model: Embedding model override

        Returns:
            Embedding vector
        """
        ...


class IEmbeddingProvider(Protocol):
    """Protocol for embedding generation.

    Separate from IOpenAIChat for flexibility (could use different providers).
    """

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (more efficient).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        ...
