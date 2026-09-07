"""OpenAI-compatible transparent proxy server for kunipy.

Mirrors the original C++ `kuni`'s proxy server: sits between an external AI
client (e.g. an IDE chat plugin) and an upstream OpenAI-compatible LLM
endpoint.

- `/v1/chat/completions` is intercepted: the character's system prompt and a
  reduced tool set (diary `ask`, and `web_search` if enabled) are injected,
  tool calls are executed locally and fed back to the upstream model in a
  loop, and only the final, clean assistant message is returned to the
  client -- it never sees the raw tool-call round-trips.
- All other routes (`/v1/embeddings`, `/v1/images/generations`, `/v1/audio/*`,
  `/v1/models`, ...) are passed through to the upstream server unmodified.

Note on streaming: incoming `stream=true` requests are honoured at the
HTTP-response level (the client gets a `text/event-stream` response, same as
talking to a real OpenAI-compatible server), but internally we run the full
non-streamed tool-calling loop first and then emit the final answer as a
single SSE chunk followed by `data: [DONE]`. This is a simplification versus
upstream token-by-token streaming, traded for a much simpler and more
robust implementation; if the client only cares about the final text (as
most do), this is indistinguishable in practice.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .character import build_system_prompt
from .config import Config, EndpointAndModel, get_config
from .diary import Diary
from .openai_chat import Message, OpenAIChat
from .tools import OpenAITools, create_ask_tool, create_web_search_tool
from .working_memory import get_working_memory

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6
LOG_DIR = Path("logs_proxy")
LAST_QUERY_PATH = Path("data/proxy/last_query.json")


def _resolve_upstream(config: Config) -> EndpointAndModel:
    """Proxy forwards to `proxy_upstream` if configured, else the main `llm`."""
    if config.proxy_upstream.endpoint.base_url:
        return config.proxy_upstream
    return config.llm


def _build_proxy_tools(diary: Optional[Diary], openai: OpenAIChat, config: Config) -> OpenAITools:
    tools = OpenAITools()
    if diary is not None:
        tools.insert(create_ask_tool(diary, openai))
    if config.capability_web_search:
        tools.insert(create_web_search_tool())
    return tools


def _log_request(name: str, payload: Any) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = LOG_DIR / f"{ts}_{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed to write proxy log: {e}")


def _save_last_query(payload: Any) -> None:
    try:
        LAST_QUERY_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_QUERY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed to write last_query.json: {e}")


def create_proxy_app(diary: Optional[Diary]) -> FastAPI:
    """Build the FastAPI app implementing the proxy server."""
    app = FastAPI(title="kunipy proxy")

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        config = get_config()
        body = await request.json()
        _log_request("request", body)
        _save_last_query(body)

        client_messages = body.get("messages", [])
        stream_requested = bool(body.get("stream", False))

        upstream_endpoint = _resolve_upstream(config)
        openai = OpenAIChat(endpoint=upstream_endpoint)
        tools = _build_proxy_tools(diary, openai, config)

        wm = get_working_memory()
        working_memory_text = str(wm.get("things_to_remember") or "")
        system_prompt = build_system_prompt(config, working_memory_text=working_memory_text)

        messages: List[Message] = []
        for m in client_messages:
            role = m.get("role", "user")
            if role == "system":
                # Fold any client-provided system message into our persona
                # instead of letting it override it.
                system_prompt = f"{system_prompt}\n\n# Client-provided instructions\n{m.get('content', '')}"
                continue
            messages.append(Message(
                role=role,
                content=m.get("content") or "",
                tool_call_id=m.get("tool_call_id"),
                tool_calls=m.get("tool_calls"),
            ))

        tool_schemas = tools.to_json_schemas()
        final_content = ""
        try:
            from .metrics import breadcrumbs
            for _ in range(MAX_TOOL_ITERATIONS):
                with breadcrumbs(chat="proxy", function="proxy_server.chat_completions"):
                    response = await openai.chat(
                        messages=messages,
                        system_prompt=system_prompt,
                        tools=tool_schemas or None,
                    )
                if not response.choices:
                    break
                choice_message = response.choices[0].get("message", {})
                content = choice_message.get("content") or ""
                tool_calls = choice_message.get("tool_calls") or None

                messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

                if not tool_calls:
                    final_content = content
                    break

                tool_results = await tools.handle_tool_calls(tool_calls, messages)
                messages.extend(tool_results)
        finally:
            await openai.close()

        response_payload = {
            "id": "chatcmpl-kunipy-proxy",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": body.get("model", upstream_endpoint.model),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": final_content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        _log_request("response", response_payload)

        if not stream_requested:
            return JSONResponse(response_payload)

        async def _sse() -> Any:
            chunk = {
                "id": response_payload["id"],
                "object": "chat.completion.chunk",
                "created": response_payload["created"],
                "model": response_payload["model"],
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": final_content},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            done_chunk = dict(chunk)
            done_chunk["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_sse(), media_type="text/event-stream")

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
    async def passthrough(path: str, request: Request) -> Response:
        """Forward any other /v1/* route to the upstream endpoint unmodified."""
        config = get_config()
        upstream_endpoint = _resolve_upstream(config)
        base_url = upstream_endpoint.endpoint.base_url.rstrip("/")
        url = f"{base_url}/{path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"

        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        if upstream_endpoint.endpoint.bearer_key:
            headers["Authorization"] = f"Bearer {upstream_endpoint.endpoint.bearer_key}"

        body = await request.body()

        async with aiohttp.ClientSession() as session:
            async with session.request(request.method, url, data=body, headers=headers) as resp:
                content = await resp.read()
                return Response(
                    content=content,
                    status_code=resp.status,
                    media_type=resp.headers.get("Content-Type", "application/json"),
                )

    return app
