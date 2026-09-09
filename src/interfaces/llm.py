"""LLM interface protocols."""

from typing import Protocol, List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass


@dataclass
class Message:
    """LLM message (user, assistant, system, tool)."""
    role: str
    content: str | List[Dict[str, Any]] = ""
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class Response:
    """LLM response."""
    content: str
    model: str
    finish_reason: str
    usage: Optional[Dict[str, int]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class IOpenAIChat(Protocol):
    """Protocol for LLM chat interface.

    Implementations: OpenAIChat (src/openai_chat.py)
    """

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
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
        messages: List[Message],
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
        model: Optional[str] = None
    ) -> List[float]:
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

    async def embed(self, text: str) -> List[float]:
        """Generate embedding vector for single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        ...

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (more efficient).

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        ...
