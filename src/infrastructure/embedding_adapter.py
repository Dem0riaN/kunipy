"""Adapter for OpenAIChat to match IEmbeddingProvider protocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..openai_chat import OpenAIChat

logger = logging.getLogger(__name__)


class OpenAIChatEmbeddingAdapter:
    """Adapter to make OpenAIChat compatible with IEmbeddingProvider protocol.

    OpenAIChat.embedding() returns np.ndarray
    IEmbeddingProvider.embed() expects list[float]

    This adapter bridges the gap.
    """

    def __init__(self, openai_chat: OpenAIChat):
        """Initialize adapter.

        Args:
            openai_chat: OpenAIChat instance with embedding() method
        """
        self.openai_chat = openai_chat

    async def embedding(self, text: str) -> list[float]:
        """Generate embedding matching legacy interface.

        Args:
            text: Input text

        Returns:
            Embedding vector as list
        """
        result = await self.openai_chat.embedding(text)
        # Convert np.ndarray to list
        if hasattr(result, 'tolist'):
            return result.tolist()
        return list(result)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding matching IEmbeddingProvider protocol.

        Args:
            text: Input text

        Returns:
            Embedding vector as list
        """
        return await self.embedding(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results

    async def close(self) -> None:
        """Close the underlying OpenAIChat HTTP session."""
        await self.openai_chat.close()
