# Documentation and implementation audit

**Audit date: 2026-09-24**

The old README was treated as documentation, not as a source of truth. Claims were checked against the current `main` implementation.

## Major corrections

### Memory

Old documentation described the new memory system as a stub. That is no longer accurate.

The current DI container creates a ChromaDB-backed `MemoryStore`, SQLite repositories, `MemoryService`, `MemoryFormationService` and working-memory storage when memory is enabled. The memory-integrated worker is then selected by the application. citeturn8view0turn8view1

A legacy `stub_store.py` remains, but it is not the current DI path. citeturn4view1

### Diary

The diary has real file and vector stores, semantic query support, dump/consolidation services and automatic RAG injection. citeturn4view2turn8view0

### Desktop

Desktop code exists, but the package explicitly describes it as stubs. It is therefore marked **In Progress**, not Ready. citeturn9view0

### Image generation

The image generator is a real Stable Diffusion WebUI-compatible integration, not merely a placeholder. It also contains a mock-image fallback path, which is not the normal configured execution path. citeturn10view0

### Voice and vision

Voice transcription, image handling and multimodal content are implemented, but provider-dependent. Animated/video stickers are explicitly unsupported. citeturn13view0

### Documents

The media extractor architecture is real, but the current default registry only registers a text extractor. This is marked **Partial**, not fully implemented document processing. citeturn8view0turn9view1turn9view2

### Web search

Web search is a real tool backed by Ollama's web-search API. citeturn11view3

### Proxy and metrics

Both are real application subsystems started from the application lifecycle when enabled. citeturn8view1

## Branch check

The `rmupgrade` branch contains the documentation revision rather than a separate implementation state. The current implementation status in this documentation is therefore based on `main`; the documentation branch is not treated as a feature branch.

## Rule for future documentation

When implementation and documentation disagree:

1. inspect the current source;
2. determine which code path is actually wired into the application;
3. distinguish real implementation from unused legacy stubs;
4. mark provider-dependent functionality explicitly;
5. only then update the documentation.

The README is an introduction. The code is the implementation reference.
