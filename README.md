# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — LLM character AI with Telegram interface, built with clean architecture and dependency injection.

**Архитектурный рефакторинг завершён (ТЗ-001):** Проект полностью переписан с использованием модульной объектно-ориентированной архитектуры (Application/Domain/Interfaces/Infrastructure), dependency injection, и Protocol-based интерфейсов. Legacy singleton-паттерны удалены.

## Status

### Implemented

- ✅ **Clean Architecture** — Application/Domain/Interfaces/Infrastructure layers
- ✅ **Dependency Injection** — Explicit constructor injection, composition root pattern
- ✅ **Protocol-based interfaces** — All major components implement typed protocols
- ✅ **Message delivery tracking** — SQLite-backed storage with 10-second verification
- ✅ Real Telegram integration via `aiotdlib`
- ✅ LLM tool-calling loop (OpenAI-compatible)
- ✅ Telegram messaging, editing, forwarding, reactions, group administration
- ✅ Photo understanding (vision)
- ✅ Voice-message transcription (hearing)
- ✅ Text-to-speech / voice-message generation
- ✅ AI image generation
- ✅ Web search
- ✅ OpenAI-compatible proxy server
- ✅ Prometheus LLM usage metrics
- ✅ Character persona and system-prompt management
- ✅ Notification queue and worker system
- ✅ Diary storage with embeddings and semantic search

### In Progress / Planned

- 🟡 **Memory system (ТЗ-002)** — Interfaces готовы, stub implementations работают; полная реализация (ChromaDB, 6-level retrieval, consolidation) запланирована
- 🟡 **Vision enhancements** — Photo understanding работает; video frame extraction не реализован
- 🟡 **Diary RAG quality** — Зависит от embedding endpoint и ingestion strategy
- 🟡 **Optional capabilities** — Vision, hearing, TTS, web search, image generation требуют внешних backends

### Not Implemented

- ❌ Video-message frame extraction
- ❌ Dedicated LLM diary-write tool
- ❌ Full C++ kuni memory workflow parity

## Requirements

- Python 3.11+
- Dependencies: `pip install -e .` (see `pyproject.toml`)
- Telegram API ID/hash from [my.telegram.org](https://my.telegram.org)
- OpenAI-compatible LLM endpoint (local Ollama, cloud provider, etc.)

## Installation

```bash
cd kunipy-main

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

## Configuration

**First run generates `config.toml`:**

```bash
python run.py
# Creates config.toml from defaults, then exits
```

Edit `config.toml` with your credentials. Minimal example:

```toml
[llm]
model = "deepseek-r1:14b"
[llm.endpoint]
base_url = "http://localhost:11434/v1/"
bearer_key = ""

[character]
name = "Куни"

[telegram]
enabled = true
api_id = 12345678
api_hash = "your_hash_from_my_telegram_org"
phone = "+79991234567"
database_directory = "data/tdlib"

[diary]
enabled = true
directory = "data/diary"
min_relatedness = 0.5

[lockdown]
mode = "papik_only"  # "none" | "contacts_only" | "papik_only"
papik_chat_id = 123456789  # Your Telegram user ID

[capabilities.hearing]
enabled = false
model = "whisper-1"
[capabilities.hearing.endpoint]
base_url = "http://localhost:11434/v1/"

[capabilities.vision]
enabled = false
model = "llava:13b"
[capabilities.vision.endpoint]
base_url = "http://localhost:11434/v1/"
```

See `config.example.toml` for full reference with bilingual (RU/EN) comments.

## Running

```bash
python run.py
```

Run from the directory containing `config.toml`. On first run with `telegram_enabled = true`, aiotdlib will prompt for:
- Phone number
- SMS/Telegram login code
- 2FA password (if enabled)

Character files (`prompts/character_base.md`, `prompts/character_appearance.md`, etc.) are loaded from `prompts/` directory.

## Architecture

Проект следует **Clean Architecture** с чётким разделением слоёв:

### Core Layers

```
┌─────────────────────────────────────────────┐
│  Application Layer (src/application/)       │
│  - lifecycle.py                             │
│  - telegram_handler.py                      │
│  - worker_orchestrator.py                   │
│  - proactive_service.py                     │
│  - sleep_scheduler.py                       │
│  - media_service.py                         │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Domain Layer (src/domain/)                 │
│  - models.py                                │
│  - delivery/models.py                       │
│  - memory/models.py                         │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Interfaces Layer (src/interfaces/)         │
│  - llm.py (IOpenAIChat)                     │
│  - telegram.py (ITelegramClient)            │
│  - memory.py (IMemoryStore, IWorkingMemory) │
│  - delivery.py (IMessageDeliveryTracker)    │
│  - worker.py (INotificationManager)         │
│  - media.py (IMediaService)                 │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Infrastructure Layer (src/infrastructure/) │
│  - delivery/                                │
│    - storage.py (SQLite WAL mode)           │
│    - tracker.py                             │
│    - telegram_checker.py                    │
│  - memory/                                  │
│    - stub_store.py (Phase 1 stub)           │
│  - worker/                                  │
│    - stub_notification_manager.py           │
└─────────────────────────────────────────────┘
```

### Key Components

- **[src/app.py](src/app.py)** — Application entry point and composition root
- **[src/config.py](src/config.py)** — Configuration management (TOML parsing, no singleton)
- **[src/worker.py](src/worker.py)** — Worker processing notifications through LLM tool-calling loop
- **[src/diary.py](src/diary.py)** — Diary/memory system with embeddings and semantic search
- **[src/di/container.py](src/di/container.py)** — Dependency injection container (composition root)
- **[src/telegram_client.py](src/telegram_client.py)** — aiotdlib/TDLib wrapper
- **[src/openai_chat.py](src/openai_chat.py)** — OpenAI-compatible API client
- **[src/tools.py](src/tools.py)** — LLM function-calling tools (Telegram actions, diary, etc.)
- **[src/character.py](src/character.py)** — Character persona and system prompt builder
- **[src/notification_manager.py](src/notification_manager.py)** — Priority queue for events
- **[src/proxy_server.py](src/proxy_server.py)** — OpenAI-compatible proxy (FastAPI)
- **[src/metrics.py](src/metrics.py)** — Prometheus metrics

### Design Principles

✅ **Dependency Injection** — Explicit constructor injection, no global singletons  
✅ **Protocol-based interfaces** — `typing.Protocol` for all major abstractions  
✅ **Single Responsibility** — Each class has one clear purpose  
✅ **Composition Root** — Dependencies wired in `di/container.py`  
✅ **Testability** — 50+ tests (integration + unit) in `tests/`  
✅ **Layer isolation** — Application → Domain → Interfaces → Infrastructure  

## Testing

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/integration/
pytest tests/unit/
pytest tests/architecture/

# Run with coverage
pytest --cov=src --cov-report=html
```

**Test coverage:**
- Integration tests: DI container, App lifecycle
- Unit tests: Worker orchestrator, Media service
- Architecture tests: Interface compliance, layer boundaries, no god objects

## Project Structure

```
kunipy-main/
├── run.py                          # Entry point
├── config.example.toml             # Configuration reference
├── pyproject.toml                  # Dependencies
├── README.md
├── .gitignore
├── src/
│   ├── app.py                      # Main application (DI-based)
│   ├── config.py                   # Configuration management
│   ├── worker.py                   # Notification worker (DI-based)
│   ├── diary.py                    # Memory/diary system (DI-based)
│   ├── character.py                # Persona management
│   ├── openai_chat.py              # LLM client
│   ├── telegram_client.py          # Telegram client
│   ├── tools.py                    # LLM function tools
│   ├── notification_manager.py     # Event queue
│   ├── proxy_server.py             # OpenAI proxy
│   ├── metrics.py                  # Prometheus metrics
│   ├── image_generator.py          # Image generation
│   ├── application/                # Application services
│   │   ├── lifecycle.py
│   │   ├── telegram_handler.py
│   │   ├── worker_orchestrator.py
│   │   ├── proactive_service.py
│   │   ├── sleep_scheduler.py
│   │   └── media_service.py
│   ├── domain/                     # Domain models
│   │   ├── models.py
│   │   ├── delivery/
│   │   └── memory/
│   ├── interfaces/                 # Protocol definitions
│   │   ├── llm.py
│   │   ├── telegram.py
│   │   ├── memory.py
│   │   ├── delivery.py
│   │   ├── worker.py
│   │   └── media.py
│   ├── infrastructure/             # Infrastructure implementations
│   │   ├── delivery/               # Message delivery tracking
│   │   ├── memory/                 # Memory stores
│   │   └── worker/                 # Worker infrastructure
│   ├── di/                         # Dependency injection
│   │   └── container.py
│   └── tests/                      # Internal tests
│       ├── architecture/
│       └── infrastructure/
├── tests/                          # Test suites
│   ├── integration/
│   │   ├── test_di_container.py
│   │   └── test_app.py
│   └── unit/
│       ├── test_worker_orchestrator.py
│       └── test_media_service.py
├── prompts/                        # Character prompts
│   ├── character_base.md
│   ├── character_appearance.md
│   ├── system.md
│   └── ...
├── data/                           # Runtime data (gitignored)
│   ├── tdlib/                      # Telegram session
│   ├── diary/                      # Diary entries
│   └── delivery.db                 # Delivery tracking
├── config/                         # Additional configs (gitignored)
└── docs/
    └── ARCHITECTURE.md             # Detailed architecture docs
```

## Development Roadmap

- ✅ **ТЗ-001: Clean Architecture** — Завершено
- 🚧 **ТЗ-002: Memory System 2.0** — В планах (ChromaDB, 6-level retrieval, consolidation)
- 🚧 **ТЗ-003: Vision 2.0** — В планах (multi-monitor, desktop vision)
- 🚧 **ТЗ-004: Avatar/Renderer** — В планах (animation, interaction, desktop UI)

## License

MIT
