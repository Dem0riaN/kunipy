"""Memory and diary tools for LLM function calling.

Provides tools for querying and storing information in the bot's memory system.
"""

import logging
from typing import Any

from ...config import get_config
from ...diary import Diary
from ...openai_chat import OpenAIChat
from .registry import Tool, ToolContext

logger = logging.getLogger(__name__)


def register_memory_tools(
    registry: Any,
    diary: Diary,
    openai: OpenAIChat,
) -> None:
    """Register memory-related tools.

    Args:
        registry: ToolRegistry instance
        diary: Diary instance for memory storage
        openai: OpenAI client for embeddings
    """

    # Ask tool - query diary/memory
    async def _ask(ctx: ToolContext) -> str:
        query_text = ctx.args["query"]
        max_entries = ctx.args.get("max_entries", 5)

        # Get embedding for the query
        embedding = await openai.embedding(query_text)
        # Search diary
        results = await diary.query(
            embedding,
            max_entries=max_entries,
            min_relatedness=get_config().diary_min_relatedness,
        )

        if not results:
            return "No relevant memories found."

        # Format results
        output_parts = ["Related memories:\n"]
        for entry, score in results:
            output_parts.append(f"--- Entry {entry.id} (relevance: {score:.3f}) ---")
            output_parts.append(entry.body)
            output_parts.append("")
        return "\n".join(output_parts)

    registry.register(
        name="ask",
        tool=Tool(
            type="function",
            function={
                "name": "ask",
                "description": (
                    "Query your diary/memory for information relevant to the current conversation. "
                    "This performs a semantic search across all your stored memories and returns the most related entries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The question or topic to search for in memory"},
                        "max_entries": {"type": "integer", "description": "Maximum number of entries to return", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        ),
        handler=_ask,
    )
