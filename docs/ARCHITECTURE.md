# Architecture

## Current shape

Kunipy currently uses a hybrid architecture.

The repository contains the following conceptual areas:

```text
src/
├── application/
├── domain/
├── interfaces/
├── infrastructure/
├── di/
├── desktop/
└── legacy/top-level modules
```

The intended dependency direction is:

```text
Application
    ↓
Interfaces ← Infrastructure
    ↓
Domain
```

The project also has a composition root in `src/app.py` and a dependency
container in `src/di/container.py`.

## Application lifecycle

`src/app.py` creates dependencies and starts enabled services.

Current startup paths include:

- worker orchestration;
- Telegram event handling;
- proactive messaging;
- sleep/consolidation scheduler;
- OpenAI-compatible proxy;
- Prometheus metrics;
- optional desktop character.

This is materially different from the older 700+ line application design
described in historical documentation: the current `app.py` is a composition
root and delegates work to focused services.

## Memory architecture

The newer memory path consists of:

- `MemoryService`;
- ChromaDB vector storage;
- SQLite repositories;
- memory formation;
- working memory;
- conversation storage;
- user/chat/preferences/tags/links.

The current `MemoryService` performs dual writes: vector memory is written to
ChromaDB and metadata is written to SQLite.

## Legacy coexistence

The architecture is not completely migrated.

Notable compatibility elements remain:

- `get_config()` still exists as a deprecated singleton compatibility path.
- `diary.py` remains a separate legacy diary implementation.
- `openai_chat.py`, `telegram_client.py`, and `tools.py` still use the legacy
  configuration accessor in places.
- The memory-integrated worker combines the newer memory system with legacy
  diary Auto-RAG.

Therefore the phrase "Clean Architecture" should be used as an architectural
direction/structure, not as a claim that every dependency is perfectly
isolated.

## Desktop character

The desktop layer exists, but the package metadata does not install a full
Live2D/PySide6 runtime by default.

The desktop package is designed around lazy imports and graceful degradation.
With the desktop feature disabled, heavy desktop dependencies are not loaded.

## Proxy

The proxy is implemented with FastAPI/Uvicorn.

`/v1/chat/completions` can inject the character system prompt and selected
tools, execute tool calls locally, and return the final assistant response.

Other OpenAI-compatible routes are forwarded upstream.

The implementation intentionally simplifies streaming: a streamed response is
represented as SSE, but the internal tool loop is completed before the final
response is emitted.
