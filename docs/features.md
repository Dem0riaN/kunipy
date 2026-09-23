# Features

This document describes features that are visible in the current codebase.
It avoids treating historical roadmap text as proof of implementation.

| Feature | Current state | Notes |
|---|---|---|
| Telegram / TDLib | Implemented | `aiotdlib` integration |
| OpenAI-compatible chat | Implemented | Async HTTP client |
| Embeddings | Implemented | OpenAI-compatible `/embeddings` |
| Character Markdown prompts | Implemented | Created if absent, existing files preserved |
| SQLite conversation history | Implemented | Part of memory infrastructure |
| ChromaDB vector memory | Implemented | Persistent vector store |
| Automatic memory formation | Implemented | LLM-based extraction path exists |
| Working memory | Implemented | In-memory/file-backed mechanisms |
| Legacy diary | Implemented | Still used alongside new memory |
| Diary Auto-RAG | Implemented | Context injection exists |
| Sleep/consolidation | Implemented | Scheduler is started when diary is available |
| Proactive messaging | Implemented | Service is started with Telegram |
| Vision | Integration | Requires a compatible multimodal backend |
| Hearing/STT | Integration | Requires a compatible transcription backend |
| TTS | Integration | ElevenLabs/OpenAI configuration paths |
| Image generation | Integration | Requires compatible backend |
| Web search | Integration | Capability/tool path exists |
| OpenAI-compatible proxy | Implemented | FastAPI/Uvicorn |
| Prometheus metrics | Implemented | `/metrics` endpoint |
| Desktop character | Experimental/scaffolded | Lazy imports and graceful degradation |
| Video frame extraction | Not verified as implemented | Do not advertise as a current feature |
| Full C++ `kuni` memory parity | Not implemented | The current Python system is its own implementation |

## External dependencies

A capability being implemented in Python does not mean it works without an
external backend.

For example:

- vision requires a vision-capable model endpoint;
- hearing requires a transcription-capable endpoint;
- TTS requires a configured provider;
- embeddings require a working embedding endpoint;
- web search requires the configured search integration.

The documentation should describe these as integrations rather than bundling
provider availability into the core project status.
