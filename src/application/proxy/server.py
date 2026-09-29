"""Proxy server FastAPI application.

Создаёт OpenAI-совместимый прокси-сервер с модульной архитектурой.
Facade для интеграции всех proxy компонентов.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ...config import get_config
from ...openai_chat import Message, OpenAIChat
from .core import ContextManager, FilterMode, ProxyCoreService, ThinkingFilter

if TYPE_CHECKING:
    from ...infrastructure.memory.diary_context_injector import DiaryContextInjector
    from ...infrastructure.memory.working_memory_file_store import WorkingMemoryFileStore
    from ...infrastructure.proxy.upstream_router import UpstreamRouter
    from .message_injector import MessageInjector
    from .rate_limiter import RateLimiter
    from .request_tracer import RequestTracer
    from .session_manager import SessionManager
    from .tool_provider import ProxyToolProvider
    from .user_context import UserContextManager

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6


def extract_user_id(request: Request) -> str:
    """Extract user ID from X-User-ID header or generate anonymous ID.

    Priority:
    1. X-User-ID header (explicit user identification)
    2. X-Forwarded-For + User-Agent hash (anonymous tracking)
    3. "anonymous" fallback

    Args:
        request: FastAPI request object

    Returns:
        User identifier string
    """
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id

    # Anonymous user: stable ID from IP + UA
    forwarded = request.headers.get("X-Forwarded-For", "")
    user_agent = request.headers.get("User-Agent", "")
    if forwarded or user_agent:
        stable_hash = hashlib.sha256(f"{forwarded}:{user_agent}".encode()).hexdigest()[:16]
        return f"anon_{stable_hash}"

    return "anonymous"


def create_proxy_application(
    session_manager: SessionManager | None = None,
    message_injector: MessageInjector | None = None,
    tool_provider: ProxyToolProvider | None = None,
    request_tracer: RequestTracer | None = None,
    wm_store: WorkingMemoryFileStore | None = None,
    injector: DiaryContextInjector | None = None,
    user_context_manager: UserContextManager | None = None,
    rate_limiter: RateLimiter | None = None,
    upstream_router: UpstreamRouter | None = None,
) -> FastAPI:
    """Create FastAPI proxy application with modular architecture.

    Args:
        session_manager: Session manager (optional, creates default)
        message_injector: Message injector (optional, creates default)
        tool_provider: Tool provider (optional, creates default)
        request_tracer: Request tracer (optional, creates default)
        wm_store: Working memory store (optional)
        injector: Diary context injector (optional)
        user_context_manager: User context manager (Phase 5, optional)
        rate_limiter: Rate limiter (Phase 5, optional)
        upstream_router: Upstream router (Phase 5, optional)

    Returns:
        Configured FastAPI application
    """
    from .message_injector import MessageInjector
    from .request_tracer import RequestTracer
    from .session_manager import SessionManager
    from .tool_provider import ProxyToolProvider

    config = get_config()

    # Initialize components with defaults if not provided
    if session_manager is None:
        session_manager = SessionManager(
            session_timeout_minutes=config.proxy_session_timeout_minutes
            if hasattr(config, "proxy_session_timeout_minutes")
            else 30
        )

    if message_injector is None:
        message_injector = MessageInjector(session_manager)

    if tool_provider is None:

        diary = None
        if config.diary_enabled:
            # Diary requires specific arguments - skip for now, tool_provider will handle None
            # In production, these should be passed from DI container
            pass
        openai = OpenAIChat()
        tool_provider = ProxyToolProvider(config, diary, openai)

    if request_tracer is None:
        request_tracer = RequestTracer()

    # Initialize core service components (ТЗ-001 §7 Application layer)
    context_manager = ContextManager(config=config, wm_store=wm_store)

    thinking_mode = getattr(config, "proxy_thinking_filter_mode", "structured")
    thinking_filter = ThinkingFilter(mode=FilterMode(thinking_mode))

    core_service = ProxyCoreService(
        config=config,
        session_manager=session_manager,
        message_injector=message_injector,
        tool_provider=tool_provider,
        context_manager=context_manager,
        thinking_filter=thinking_filter,
        diary_injector=injector,
    )

    app = FastAPI(title="kunipy-proxy")

    @app.websocket("/v1/ws/chat")
    async def websocket_chat_endpoint(websocket: WebSocket):
        """WebSocket endpoint for Open-LLM-VTuber integration.

        Phase 2: WebSocket adapter implementation.
        Protocol: Open-LLM-VTuber bidirectional streaming.
        """
        if not getattr(config, "proxy_websocket_enabled", False):
            await websocket.close(code=1008, reason="WebSocket not enabled")
            return

        from .websocket_adapter import WebSocketProxyAdapter

        # Extract user ID from query params or headers
        user_id = websocket.query_params.get("user_id", "vtuber_user")

        # Create adapter
        adapter = WebSocketProxyAdapter(core_service, user_id)

        # Handle connection
        await adapter.handle_connection(websocket)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        """Handle chat completions with tool calling loop."""
        config = get_config()
        body = await request.json()

        # Phase 5: Extract user ID
        user_id = extract_user_id(request)

        # Phase 5: Check rate limit
        if rate_limiter:
            allowed, error_msg = await rate_limiter.check_rate_limit(user_id)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "message": error_msg,
                            "type": "rate_limit_exceeded",
                            "code": "rate_limit_exceeded",
                        }
                    },
                )

        # Trace incoming request
        request_tracer.trace_client_to_proxy(body)

        client_messages = body.get("messages", [])
        stream_requested = bool(body.get("stream", False))

        # Convert to Message objects
        messages: list[Message] = []
        for m in client_messages:
            role = m.get("role", "user")
            if role == "system":
                # System messages handled separately
                continue
            messages.append(
                Message(
                    role=role,
                    content=m.get("content") or "",
                    tool_call_id=m.get("tool_call_id"),
                    tool_calls=m.get("tool_calls"),
                )
            )

        # Get or create session (with user context if available)
        if user_context_manager:
            session = await user_context_manager.get_user_session(user_id, messages)
        else:
            session = session_manager.get_or_create(messages, user_id)

        # Resolve user context (papik identification, cross-channel memory)
        user_context = await core_service.resolve_user_context(
            user_id=user_id,
            headers=dict(request.headers),
        )

        # Merge hidden context (tool calls from previous turns)
        messages_with_context = core_service.merge_hidden_context(messages, session.session_id)

        # Inject diary context
        diary_context = await core_service.inject_diary_context(messages_with_context)

        # Build system prompt with user context
        system_prompt = core_service.build_system_prompt(user_context, diary_context)

        # Fold any client-provided system message into persona
        client_system_instructions = ""
        for m in client_messages:
            if m.get("role") == "system":
                client_system_instructions = m.get("content", "")

        if client_system_instructions:
            system_prompt = f"{system_prompt}\n\n# Client-provided instructions\n{client_system_instructions}"

        # Get upstream endpoint (Phase 5: Route through UpstreamRouter if available)

        if upstream_router:
            # Phase 5: Multi-upstream routing based on request path
            upstream_config = upstream_router.get_upstream(request.url.path)
            upstream_endpoint = upstream_config.endpoint
            logger.debug(f"Routed {request.url.path} to upstream: {upstream_config.name}")
        else:
            # Fallback to single upstream (backward compatibility)
            upstream_endpoint = _resolve_upstream(config)

        openai = OpenAIChat(endpoint=upstream_endpoint)

        # Get tool schemas
        tool_schemas = tool_provider.get_tool_schemas()

        # Tool calling loop
        final_content = ""
        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                logger.debug(f"Tool iteration {iteration + 1}/{MAX_TOOL_ITERATIONS}")

                # Call LLM
                response = await openai.chat(
                    messages=messages_with_context,
                    system_prompt=system_prompt,
                    tools=tool_schemas,
                )

                if not response.choices:
                    break

                choice_message = response.choices[0].get("message", {})
                content = choice_message.get("content") or ""
                tool_calls = choice_message.get("tool_calls")

                # Append assistant message
                assistant_msg = Message(role="assistant", content=content, tool_calls=tool_calls)
                messages_with_context.append(assistant_msg)

                # If no tool calls, we're done
                if not tool_calls:
                    final_content = content
                    break

                # Execute tool calls
                tool_results = await tool_provider.execute_tool_calls(tool_calls, messages_with_context)
                messages_with_context.extend(tool_results)

                # Store hidden context (assistant + tool results)
                message_injector.store_tool_context(session.session_id, assistant_msg, tool_results)

        except Exception:
            logger.exception("Error in tool calling loop")
            final_content = "Error occurred while generating response. See the logs for details."
        finally:
            await openai.close()

        # Filter thinking from final response (ТЗ-001 Problem 1 solution)
        filtered = core_service.filter_response(final_content)
        if filtered.thinking:
            logger.debug(f"Filtered thinking ({len(filtered.thinking)} chars): {filtered.thinking[:100]}...")

        # Phase 5: Record request for rate limiting
        if rate_limiter:
            await rate_limiter.record_request(user_id)

        # Build response
        response_payload = {
            "id": "chatcmpl-kunipy-proxy",
            "object": "chat.completion",
            "created": int(datetime.now(UTC).timestamp()),
            "model": body.get("model", upstream_endpoint.model),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": filtered.content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        # Trace response
        request_tracer.trace_proxy_to_client(response_payload, session.session_id)

        if not stream_requested:
            return JSONResponse(response_payload)

        # True incremental streaming with StreamingFilter
        from .streaming_filter import StreamingFilter

        streaming_filter = StreamingFilter(session_manager, thinking_filter)

        async def _incremental_sse():
            """Stream response with real-time tool call filtering."""
            # Create a new OpenAIChat instance for streaming
            openai_stream = OpenAIChat(endpoint=upstream_endpoint)
            try:
                # Call LLM with streaming enabled
                stream_response = await openai_stream.chat(
                    messages=messages_with_context,
                    system_prompt=system_prompt,
                    tools=tool_schemas,
                    stream=True,
                )

                # Process chunks in real-time
                async for chunk in stream_response:
                    # Convert StreamingChunk to SSE format
                    chunk_dict = {
                        "id": response_payload["id"],
                        "object": "chat.completion.chunk",
                        "created": response_payload["created"],
                        "model": response_payload["model"],
                        "choices": [{
                            "index": 0,
                            "delta": chunk.delta,
                            "finish_reason": chunk.finish_reason,
                        }]
                    }

                    # Filter through StreamingFilter
                    filtered_chunk, hidden_messages = await streaming_filter.filter_chunk(
                        chunk_dict,
                        session.session_id
                    )

                    # Store hidden tool calls in session
                    if hidden_messages:
                        for hidden_msg in hidden_messages:
                            message_injector.store_tool_context(
                                session.session_id,
                                hidden_msg,
                                []  # Tool results will be added after execution
                            )
                            logger.info(
                                f"Filtered tool call in streaming: "
                                f"{hidden_msg.get('tool_calls', [{}])[0].get('function', {}).get('name', 'unknown')} "
                                f"(session {session.session_id})"
                            )

                    # Yield filtered chunk to client
                    if filtered_chunk:
                        yield f"data: {json.dumps(filtered_chunk, ensure_ascii=False)}\n\n"

                # Send [DONE] marker
                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.exception("Streaming error")
                # Send error chunk
                error_chunk = {
                    "id": response_payload["id"],
                    "object": "chat.completion.chunk",
                    "created": response_payload["created"],
                    "model": response_payload["model"],
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n\n[Error: {e!s}]"},
                        "finish_reason": "error",
                    }]
                }
                yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                # Close the streaming session
                await openai_stream.close()

        return StreamingResponse(_incremental_sse(), media_type="text/event-stream")

    @app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def passthrough(path: str, request: Request) -> Response:
        """Forward other /v1/* routes to upstream unmodified."""
        import aiohttp

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

        async with aiohttp.ClientSession() as session, session.request(
            request.method, url, data=body, headers=headers
        ) as resp:
            content = await resp.read()
            return Response(
                content=content,
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
            )

    return app


def _resolve_upstream(config):
    """Resolve upstream endpoint (proxy_upstream or main llm)."""
    if config.proxy_upstream.endpoint.base_url:
        return config.proxy_upstream
    return config.llm
