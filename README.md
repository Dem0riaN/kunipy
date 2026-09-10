# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — LLM character AI with Telegram interface, built with clean architecture and dependency injection.

**Status: PRODUCTION READY** — Clean Architecture реализована, DI container работает, dual memory system (legacy + ChromaDB) полностью функциональна. ТЗ-001/ТЗ-001.01 выполнено на 100%.

---

## 🚨 Важно: Dual Memory System

В kunipy **работают ДВЕ системы памяти одновременно**:

### 1. Legacy Diary (Старая система)
- ✅ Работает из коробки с существующими `*.md` файлами
- Директория: `config.diary_dir` (например, `./diary/`)
- Активация: `diary.enabled = true` в config.toml
- **Миграция НЕ требуется** — продолжает работать с текущими данными

### 2. New Memory System (ChromaDB)
- ✅ Полностью интегрирована в DI container
- Директория: `data/chroma/` (автоматически создаётся)
- Активация: Всегда активна
- Semantic search, embeddings, multi-level memory

### Как использовать?

**Вариант 1: Продолжить со старыми данными (рекомендуется)**
```toml
[diary]
enabled = true
directory = "./diary"
```
Старая система работает как раньше. **Миграция не нужна.**

**Вариант 2: Мигрировать в ChromaDB (опционально)**
```bash
# Одна команда для миграции
python migrate_diary.py --kuni-dir ./diary

# Проверка перед миграцией
python migrate_diary.py --kuni-dir ./diary --dry-run

# После миграции можно отключить старую систему
[diary]
enabled = false
```

**Вариант 3: Только новая система (чистый старт)**
```toml
[diary]
enabled = false
```

---

## Status

### Implemented ✅

**Architecture:**
- ✅ Clean Architecture (4 слоя: Application/Domain/Interfaces/Infrastructure)
- ✅ Dependency Injection (explicit constructor injection, composition root)
- ✅ Protocol-based interfaces (все компоненты используют typed protocols)
- ✅ God Objects устранены (app.py: 728→238 lines)

**Memory System:**
- ✅ **Dual Memory** — Legacy Diary + ChromaDB работают параллельно
- ✅ **MemoryStore** — ChromaDB-based persistent storage
- ✅ **WorkingMemory** — In-memory working context
- ✅ **VectorStore** — ChromaDB wrapper с semantic search
- ✅ **EmbeddingCache** — TTL-based cache для embeddings
- ✅ **Migration CLI** — Одна команда для миграции C++ kuni diary

**Core Features:**
- ✅ Message delivery tracking (SQLite WAL + 10-second verification)
- ✅ Telegram integration via aiotdlib
- ✅ LLM tool-calling loop (OpenAI-compatible)
- ✅ Photo understanding (vision)
- ✅ Voice transcription (hearing)
- ✅ Text-to-speech generation
- ✅ AI image generation
- ✅ Web search
- ✅ OpenAI-compatible proxy server
- ✅ Prometheus metrics
- ✅ Character persona system

**Quality:**
- ✅ Ruff = 0 errors
- ✅ Type hints 100%
- ✅ Integration tests (memory, delivery, DI)
- ✅ Architecture tests (layer boundaries, protocols)

### Not Implemented ❌

- ❌ Video-message frame extraction
- ❌ Dedicated LLM diary-write tool

---

## Requirements

- Python 3.11+
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- OpenAI-compatible LLM endpoint (Ollama, cloud provider, etc.)

---

## Installation

```bash
cd kunipy-main

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

---

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
nickname = ""               # Опциональное короткое имя

# Owner configuration (важно!)
papik_name = "Папик"        # Имя владельца (используется в промптах)
papik_chat_id = 123456789   # Telegram user ID владельца (обязательно!)

[telegram]
enabled = true
api_id = 12345678
api_hash = "your_hash_from_my_telegram_org"
phone = "+79991234567"
database_directory = "data/tdlib"

[diary]
enabled = true              # Legacy diary (опционально)
directory = "diary"         # Где лежат существующие .md файлы
min_relatedness = 0.5

# Новая ChromaDB память работает автоматически в data/chroma/

[lockdown]
mode = "papik_only"         # "none" | "contacts_only" | "papik_only"
# papik_chat_id берётся из секции [character]

[capabilities.hearing]
enabled = false
model = "whisper-1"
[capabilities.hearing.endpoint]
base_url = "http://localhost:11434/v1/"

[capabilities.vision]
enabled = false
model = "gpt-4-vision-preview"

[capabilities.image_generation]
enabled = false

[capabilities.web_search]
enabled = false
```

---

## Usage

### Start the bot

```bash
python run.py
```

First run:
1. Creates `config.toml` if missing
2. Initializes Telegram session (asks for phone code)
3. Loads character prompts from `prompts/`
4. Starts listening to Telegram messages

### Migration from C++ kuni (Optional)

```bash
# Автоматическая миграция diary из C++ kuni в ChromaDB
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary

# Dry-run (проверка без записи)
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --dry-run

# С custom output директорией
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --output-dir ./data/custom

# Verbose output
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --verbose
```

**Миграция:**
- Копирует данные в ChromaDB (оригиналы не изменяются)
- Генерирует embeddings через configured LLM
- Показывает progress bar и статистику
- **Опциональна** — старая система работает без миграции

---

## Architecture

kunipy follows **Clean Architecture** with 4 layers:

```
┌─────────────────────────────────────────┐
│       Application Layer                 │
│  - ApplicationLifecycle                 │
│  - TelegramEventHandler                 │
│  - Worker                               │
└─────────────────────────────────────────┘
              ↓ uses protocols
┌─────────────────────────────────────────┐
│       Interfaces Layer                  │
│  - IMemoryStore                         │
│  - IWorkingMemory                       │
│  - IOpenAIChat                          │
│  - ITelegramClient                      │
│  - IMessageDeliveryTracker              │
└─────────────────────────────────────────┘
              ↑ implemented by
┌─────────────────────────────────────────┐
│     Infrastructure Layer                │
│  Memory:                                │
│  ├─ MemoryStore (ChromaDB)             │
│  ├─ WorkingMemory (in-memory)          │
│  └─ Diary (legacy, optional)           │
│                                         │
│  Delivery:                              │
│  ├─ MessageDeliveryStorage (SQLite)    │
│  └─ MessageDeliveryTracker             │
│                                         │
│  LLM:                                   │
│  └─ OpenAIChat                          │
│                                         │
│  Telegram:                              │
│  └─ TelegramClient (TDLib)             │
└─────────────────────────────────────────┘
```

### Directory Structure

```
src/
├── interfaces/              # Protocol definitions
│   ├── llm.py              # IOpenAIChat, IEmbeddingProvider
│   ├── telegram.py         # ITelegramClient, ITelegramMessageService
│   ├── memory.py           # IMemoryStore, IWorkingMemory
│   ├── delivery.py         # IMessageDeliveryTracker
│   └── ...
│
├── domain/                  # Business models
│   ├── models.py           # TelegramMessage, User, Chat
│   ├── memory/
│   │   └── models.py       # MemoryPiece, MemoryScope, MemoryKind
│   └── delivery/
│       └── models.py       # MessageDeliveryRecord, DeliveryState
│
├── application/             # Use cases and orchestration
│   ├── lifecycle.py        # ApplicationLifecycle
│   ├── telegram_handler.py # TelegramEventHandler
│   └── worker_orchestrator.py
│
├── infrastructure/          # External system implementations
│   ├── memory/             # ✅ Memory infrastructure (ТЗ-001 complete)
│   │   ├── vector_store.py    # ChromaDB wrapper
│   │   ├── storage.py         # MemoryStore implementation
│   │   ├── working_memory.py  # WorkingMemory implementation
│   │   └── embedding_cache.py # TTL-based cache
│   ├── delivery/           # ✅ Delivery tracking (ТЗ-001 complete)
│   │   ├── storage.py         # SQLite WAL storage
│   │   ├── tracker.py         # Delivery coordinator
│   │   └── telegram_checker.py # 10-second verification
│   └── ...
│
├── di/                      # Dependency injection
│   └── container.py        # Dependencies, create_dependencies()
│
├── diary.py                # Legacy diary system (optional)
├── app.py                  # Composition root (thin, 238 lines)
├── worker.py               # Worker implementation
└── tools.py                # LLM tools

tests/
├── architecture/           # Architecture compliance tests
│   ├── test_layer_boundaries.py
│   ├── test_no_god_objects.py
│   └── test_interface_compliance.py
└── integration/
    ├── test_memory_integration.py    # Memory + DI tests
    ├── test_di_container.py
    └── test_app.py

prompts/                    # Character prompts
├── character_base.md
├── character_appearance.md
├── system.md
└── ...

data/                       # Runtime data (gitignored)
├── chroma/                # Новая memory система (автоматически)
├── delivery.db            # Delivery tracking
└── tdlib/                 # Telegram session

diary/                      # Legacy diary (если enabled)
└── *.md                   # ~1200 файлов
```

Character files (`prompts/character_base.md`, `prompts/character_appearance.md`, etc.) are loaded from `prompts/` directory.

---

## Testing

```bash
# All tests
pytest

# Memory integration tests
pytest tests/integration/test_memory_integration.py -v

# Architecture tests
pytest tests/architecture/ -v

# With coverage
pytest --cov=src --cov-report=html
```

---

## Development

### Code Quality

```bash
# Ruff linting
ruff check .

# Type checking
mypy src/

# Format code
ruff format .
```

### Project Status

- **ТЗ-001:** ✅ 100% Complete (Clean Architecture + Memory System)
- **ТЗ-001.01:** ✅ 100% Complete (Code Quality)
- **Ruff errors:** 0
- **Type coverage:** 100%
- **Architecture tests:** Passing
- **Integration tests:** Passing

---

## Documentation

- [CURRENT_STATE.md](CURRENT_STATE.md) — **Актуальное состояние проекта (читать первым)**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Детальная архитектура
- [docs/MIGRATION.md](docs/MIGRATION.md) — Руководство по миграции
- [STATUS_COMPLETE.md](STATUS_COMPLETE.md) — ТЗ-001 completion report

---

## FAQ

### Нужно ли мигрировать старые diary данные?
**Нет.** Старая система работает как раньше. Миграция опциональна.

### Можно ли использовать обе системы памяти?
**Да.** Legacy Diary и ChromaDB работают параллельно без конфликтов.

### Что происходит при миграции?
Данные **копируются** в ChromaDB. Оригинальные файлы остаются нетронутыми как backup.

### Какую систему памяти выбрать?
- **Legacy Diary:** Проверенная, работает "из коробки", не требует настройки
- **ChromaDB:** Semantic search, быстрее, готова к multi-level memory
- **Обе:** Можно использовать гибридный режим

### Как отключить старую систему после миграции?
```toml
[diary]
enabled = false
```
Файлы остаются на диске как backup.

---

## License

See original [kuni](https://github.com/alex2772/kuni) project.

---

**Version:** Production Ready  
**Last Updated:** 2026-09-10  
**Status:** ТЗ-001/ТЗ-001.01 Complete
