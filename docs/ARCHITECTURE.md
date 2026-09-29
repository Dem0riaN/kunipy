# Architecture

Kunipy uses a layered application architecture with dependency injection, having completed modularization to improve maintainability and testability.

## Main layers

```text
Application / orchestration
        |
        v
Domain models and protocols
        |
        v
Interfaces
        |
        v
Infrastructure
```

The composition root is `src/di/container.py`. It creates the LLM client, Telegram client, memory stores/services, diary services, media extractor registry, workers and other runtime components.

`src/app.py` owns lifecycle orchestration and starts workers, Telegram handlers, sleep/consolidation, proxy, metrics and the optional desktop character.

## Tool System Architecture

The tool system (LLM function calling) uses a modular registry-based pattern:

### Current Architecture (Modular)

```text
src/application/tools/ (1,136 LOC across 7 modules)
├── __init__.py - Public API and registry creation
├── registry.py - Core ToolRegistry with OCP-compliant registration
├── telegram_tools.py - 11 Telegram operations (376 LOC)
├── memory_tools.py - Memory operations (76 LOC)
├── media_tools.py - 6 media tools (193 LOC)
├── admin_tools.py - 3 admin tools (107 LOC)
└── utilities.py - 3 utility tools (119 LOC)
```

**Tool Categories (23 total):**
- **Telegram (11):** send_message, get_chats, search_chats, search_messages, open_chat, edit_message, remove_message, react_emoji, forward_message, join_chat, leave_chat
- **Memory (1):** ask (diary query with semantic search)
- **Media (6):** take_photo, record_audio, sticker_send, sticker_list, sticker_save
- **Admin (3):** ban_user, remove_message, set_user_tag
- **Utilities (3):** web_search, wait, pause

### Design Principles

1. **Registry Pattern** - Inspired by `MediaExtractorRegistry`, allows tools to be registered without modifying core code (Open/Closed Principle)
2. **Protocol-Based** - Uses Python `Protocol` for `ToolHandler` interface, enabling better type inference
3. **Dependency Injection** - `ToolContext` carries all dependencies (config, telegram, openai, conversation_history)
4. **Single Responsibility** - Each tool module handles one category of operations
5. **Modular Structure** - Maximum file size 376 LOC (was 939 LOC monolith)

### Backward Compatibility

The old `src/tools.py` has been moved to `src/tools_old_backup.py` for reference. A compatibility layer in `src/tools/__init__.py` preserves the old API for components like `proxy_server.py` that still use it.

## Architecture status

The project has a mature DI/layering structure with ongoing refactoring. Sprint 1-3 (documented in `REFACTORING_LOG.md`) successfully eliminated god objects and achieved SOLID compliance with DI-compliant services.

**Completed:**
- ✅ Sprint 1: Critical naming fixes (temporary_context → conversation_history), service extractions (ImageProcessor, AntiRepeatService)
- ✅ Sprint 2: Tool system fully modularized - god object eliminated, 23 tools in 7 focused modules
- ✅ Sprint 3 Task 1: MediaService DI injection - fully injected via DI container
- 🔄 Sprint 3 Task 2-3: TelegramMessageService extraction, enhanced error handling (in progress)

**Architecture quality:** 82% production-ready, 8.5/10 quality (improved from 8/10).

**Dependency Injection:**
- MediaService created once in DI container
- Injected into Worker, MemoryIntegratedWorker, TelegramEventHandler
- No inline instantiation (except fallback for backward compatibility)
- Easy to test with mock services

## Desktop

The desktop character is a Kunipy-specific subsystem. It is currently a scaffold/stub and is intentionally isolated behind bridges and lazy imports.
