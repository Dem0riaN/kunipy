"""Proxy server application layer.

Модульная архитектура для OpenAI-совместимого прокси-сервера.
Следует принципам ТЗ-001: separation of concerns, DI, extensibility.

Phase 1: Foundation (SessionManager, MessageInjector, ToolProvider, RequestTracer)
Phase 2: Integration Tests
Phase 3: True Incremental Streaming (StreamingFilter)
Phase 4: Context Persistence (ContextPersistence)
Phase 5: Open-LLM-VTuber Integration (UserContextManager, RateLimiter)
"""

from .context_persistence import ContextPersistence
from .message_injector import MessageInjector
from .rate_limiter import RateLimitConfig, RateLimiter
from .request_tracer import RequestTracer
from .server import create_proxy_application
from .session_manager import ProxySession, SessionManager
from .streaming_filter import StreamingFilter
from .tool_provider import ProxyToolProvider
from .user_context import UserContext, UserContextManager

__all__ = [
    "ContextPersistence",
    "MessageInjector",
    "ProxySession",
    "ProxyToolProvider",
    "RateLimitConfig",
    "RateLimiter",
    "RequestTracer",
    "SessionManager",
    "StreamingFilter",
    "UserContext",
    "UserContextManager",
    "create_proxy_application",
]
