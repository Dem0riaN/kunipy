"""Utility tools and helpers for LLM function calling.

Provides web search, flow control (wait/pause), and other utility tools.
"""

import logging
from typing import Any

import aiohttp

from ...config import get_config
from .registry import Tool, ToolContext

logger = logging.getLogger(__name__)


def register_utility_tools(
    registry: Any,
) -> None:
    """Register utility tools (web search, wait, pause).

    Args:
        registry: ToolRegistry instance
    """
    config = get_config()

    # Web search tool
    if config.capability_web_search:
        async def _web_search(ctx: ToolContext) -> str:
            query = ctx.args["query"]
            max_results = ctx.args.get("max_results", 5)

            headers = {"Content-Type": "application/json"}
            if config.web_search_ollama_key:
                headers["Authorization"] = f"Bearer {config.web_search_ollama_key}"

            try:
                async with aiohttp.ClientSession() as session, session.post(
                    "https://ollama.com/api/web_search",
                    json={"query": query, "max_results": max_results},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        return f"Error: web search failed ({resp.status}): {err[:300]}"
                    data = await resp.json()
            except (ValueError, KeyError, TypeError, RuntimeError) as e:
                return f"Error: web search request failed: {e}"

            results = data.get("results", [])
            if not results:
                return f"No web search results found for: {query}"

            parts = [f"Web search results for: {query}\n"]
            for r in results[:max_results]:
                title = r.get("title", "")
                url = r.get("url", "")
                content = (r.get("content") or "")[:400]
                parts.append(f"- {title} ({url})\n  {content}")
            return "\n".join(parts)

        registry.register(
            name="web_search",
            tool=Tool(
                type="function",
                function={
                    "name": "web_search",
                    "description": "Search the web for current information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"},
                            "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
                        },
                        "required": ["query"],
                    },
                },
            ),
            handler=_web_search,
        )

    # Wait tool - signals LLM is done with current turn
    async def _wait(ctx: ToolContext) -> str:
        return "Success"

    registry.register(
        name="wait",
        tool=Tool(
            type="function",
            function={
                "name": "wait",
                "description": "Wait until further notifications. Call this when you have nothing more to do on the current turn.",
                "parameters": {"type": "object", "properties": {}},
            },
        ),
        handler=_wait,
    )

    # Pause tool - alias for wait
    async def _pause(ctx: ToolContext) -> str:
        return "Success"

    registry.register(
        name="pause",
        tool=Tool(
            type="function",
            function={
                "name": "pause",
                "description": "Pauses the conversation.",
                "parameters": {"type": "object", "properties": {}},
            },
        ),
        handler=_pause,
    )


# Terminal tool names for worker to detect
TERMINAL_TOOL_NAMES = frozenset({"wait", "pause"})
