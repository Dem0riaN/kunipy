# Project status

**Status reviewed against the current `main` implementation: 2026-09-24.**

The status below is based on the implementation, not on the old README. A feature is marked **Ready** when a real implementation is present in the current code path. External-provider features are marked ready with an asterisk because they require a backend/configuration. A feature is **Partial** when only part of the requested scope is implemented. **In progress** means there is active project code but it is explicitly a scaffold/stub or incomplete. **Planned** means the repository itself identifies the missing functionality as future work.

## ✅ Ready

### Core

- AI character/personality prompt system
- OpenAI-compatible chat client
- Streaming responses
- OpenAI-compatible tool calling
- Dependency injection / composition root
- Application lifecycle and graceful shutdown
- Notification queue and worker orchestration

The application selects `MemoryIntegratedWorker` when the new memory services are enabled. citeturn8view1turn8view0

### Telegram

The repository contains a real asynchronous TDLib client through `aiotdlib`, including authentication, message handling, chat operations, reactions, stickers, forwarding, editing and administrative operations. citeturn13view1

### Character

Character identity and appearance are stored in editable Markdown files. They are created with defaults if absent and loaded into the system prompt. Existing files are not overwritten. citeturn10view2

### Diary

The diary has file storage, ChromaDB-backed vector search, legacy fallback behaviour, automatic dump/consolidation components and RAG context injection. The current DI container actually wires the file and vector stores, dump service, context injector and consolidation service. citeturn4view2turn8view0

### Long-term memory

The new memory system is implemented and wired into the application:

- ChromaDB vector storage;
- SQLite metadata/history;
- conversation repository;
- memory links/tags;
- user/chat repositories;
- working memory;
- embedding provider;
- automatic memory formation.

The `MemoryService` performs real dual writes and multi-scope retrieval. The application creates it when memory is enabled and passes it to `MemoryIntegratedWorker`. citeturn4view0turn8view0turn9view3

### Automatic memory formation

`MemoryFormationService` sends recent conversation content to the configured LLM, parses structured JSON memory items, creates typed memory pieces, generates embeddings and stores them through the memory service. citeturn9view4turn9view3

### Working memory

Working memory is implemented with file persistence and is used by the memory service and worker. Promises, plans and current context are available to the prompt-building path. citeturn4view0turn8view0

### Sleep / consolidation

A real `SleepConsolidationService` is present and is wired into the diary when diary support is enabled. The scheduler starts the consolidation flow as a background service. citeturn9view5turn8view4turn8view0

### Media

Real processing exists for:

- Telegram voice-message download and transcription;
- image download for photos/static stickers;
- multimodal image input;
- text document extraction;
- media extractor registry.

The current registry has a real `TxtExtractor`; animated/video stickers are explicitly unsupported. citeturn13view0turn9view1turn9view2

### TTS

The `record_audio` tool calls the configured OpenAI-compatible speech synthesis path, writes the result to `data/generated_audio`, and can send it as a Telegram voice message. citeturn11view3turn10view1

### Image generation

`take_photo` is a real Stable Diffusion WebUI-compatible `txt2img` integration. It generates and saves an image and can send it to Telegram. The feature is provider-dependent. citeturn10view0turn10view1

### Web search

A real `web_search` tool calls Ollama's web-search API and returns result titles, URLs and snippets. It is enabled conditionally through configuration. citeturn11view3

### Proxy and metrics

The application contains a real OpenAI-compatible proxy server and Prometheus metrics server, both started from the application lifecycle when enabled. citeturn8view1turn4view4

## 🟡 Partial

### Document processing

Document extraction is implemented as an extensible registry, but the current DI container registers `TxtExtractor`. This means generic document processing exists as infrastructure, while broad PDF/Office/archive/etc. extraction is not yet represented by the current default registry. citeturn8view0turn9view1turn9view2

### Vision

Photo understanding is implemented, including image download and a legacy dedicated vision endpoint. The main LLM client also supports OpenAI-format multimodal message content. However, animated/video stickers are explicitly unsupported and there is no general video-frame pipeline in the current media service. citeturn13view0turn13view2

## 🚧 In progress

### Desktop character

The desktop subsystem exists, but the package itself explicitly describes the current `DesktopCharacter` implementation as a **stub**. It is designed for lazy PySide6/Cubism/OpenGL integration and graceful degradation, but it should not be presented as a finished desktop avatar. citeturn9view0

The application can attempt to start the desktop character when `desktop_enabled` is set, but failures are intentionally caught so the main application continues running. citeturn8view1

### Live2D / renderer

The desktop architecture contains bridges and a character layer intended to host the future renderer. This belongs to Kunipy's own development direction and is not an inherited Kuni feature.

## 📋 Planned / not implemented

### Video-message frame extraction

The current media service explicitly supports photos and static stickers for vision and rejects animated/video stickers. A general video-frame extraction pipeline is not implemented. citeturn13view0

### Expanded document extractors

The extractor registry is ready for additional implementations, but the current default registration only installs `TxtExtractor`. citeturn8view0turn9view1

### Full desktop avatar

A complete Live2D/Cubism/PySide6 desktop character with rendering, animation and interaction is not finished.

## Important distinction: old stubs

There is still a file named `src/infrastructure/memory/stub_store.py`. It is a legacy/in-memory stub and its own docstring says it is temporary. **It is not the implementation used by the current DI container.**

The current container imports `MemoryStore` and `WorkingMemory` from `src/infrastructure/memory` and wires the ChromaDB-backed memory service. Therefore the existence of `stub_store.py` must not be used as evidence that the current long-term memory system is still a stub. citeturn4view1turn8view0

## Status legend

- ✅ **Ready** — real implementation is present in the current application path.
- 🟡 **Partial** — real implementation exists, but only part of the intended scope is covered.
- 🚧 **In progress** — active code exists, but it is explicitly incomplete/scaffolded.
- 📋 **Planned** — not implemented in the current code path.
