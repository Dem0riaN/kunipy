# kunipy Architecture Guide

**Version**: Hybrid Memory + Autonomy Features  
**Last Updated**: 2026-09-19

---

## Overview

kunipy follows **Clean Architecture** principles with clear layer separation and dependency inversion. The architecture is designed to support:

- Multi-level memory system (ТЗ-002)
- Telegram delivery tracking (ТЗ-001)
- Multi-channel communication (desktop/telegram/voice)
- Modular, testable, maintainable codebase

---

## Layer Architecture

```
┌─────────────────────────────────────────┐
│       Application Layer                 │
│  (Use Cases, Orchestration)             │
│  - ApplicationLifecycle                 │
│  - WorkingMemoryUpdateService           │
│  - DiaryDumpService                     │
│  - TelegramEventHandler                 │
│  - WorkerOrchestrator                   │
│  - SleepScheduler                       │
│  - ProactiveMessageService              │
└─────────────────────────────────────────┘
              ↓ depends on
┌─────────────────────────────────────────┐
│         Domain Layer                    │
│  (Business Logic, Models)               │
│  - TelegramMessage                      │
│  - MemoryPiece, MemoryScope             │
│  - MessageDeliveryRecord                │
│  - User, Chat, Conversation             │
└─────────────────────────────────────────┘
              ↓ depends on
┌─────────────────────────────────────────┐
│       Interfaces Layer                  │
│  (Protocols, Abstractions)              │
│  - IOpenAIChat                          │
│  - ITelegramClient                      │
│  - IMemoryStore                         │
│  - IMessageDeliveryTracker              │
└─────────────────────────────────────────┘
              ↑ implemented by
┌─────────────────────────────────────────┐
│     Infrastructure Layer                │
│  (External Systems, Frameworks)         │
│  - OpenAIChat (LLM)                     │
│  - TelegramClient (TDLib)               │
│  - MemoryService (dual-write API)       │
│    ├─ MemoryStore (ChromaDB vectors)    │
│    └─ SQLite repositories (metadata)    │
│  - DeliveryTracker (Telegram API)       │
└─────────────────────────────────────────┘
```

---

## Dependency Rules

### ✅ Allowed Dependencies

1. **Application** → Interfaces + Domain
2. **Domain** → (nothing - pure business logic)
3. **Infrastructure** → Interfaces + Domain
4. **Interfaces** → Domain (for types only)

### ❌ Forbidden Dependencies

1. **Domain** → Infrastructure ❌
2. **Domain** → Application ❌
3. **Interfaces** → Infrastructure ❌
4. **Application** → Infrastructure (direct) ❌

**Rule**: Dependencies point **INWARD** only. Infrastructure depends on Domain, never the reverse.

---

## Directory Structure

```
src/
├── interfaces/              # Protocol definitions
│   ├── __init__.py
│   ├── llm.py              # IOpenAIChat, IEmbeddingProvider
│   ├── telegram.py         # ITelegramClient, ITelegramMessageService
│   ├── memory.py           # IMemoryStore, IWorkingMemory
│   ├── delivery.py         # IMessageDeliveryTracker
│   ├── worker.py           # INotificationManager
│   └── media.py            # IMediaHandler, IVisionService
│
├── domain/                  # Business models
│   ├── __init__.py
│   ├── models.py           # TelegramMessage, User, Chat, etc.
│   ├── memory/
│   │   ├── __init__.py
│   │   └── models.py       # MemoryPiece, MemoryScope, etc.
│   └── delivery/
│       ├── __init__.py
│       └── models.py       # MessageDeliveryRecord, DeliveryState
│
├── application/             # Use cases and orchestration
│   ├── __init__.py
│   ├── lifecycle.py        # ApplicationLifecycle
│   ├── working_memory_update_service.py # Working memory extraction
│   ├── diary_dump_service.py # Autonomous diary saving
│   ├── telegram_handler.py # TelegramEventHandler
│   ├── worker_orchestrator.py
│   ├── sleep_scheduler.py
│   └── proactive_service.py
│
├── infrastructure/          # External system implementations
│   ├── __init__.py
│   ├── telegram_client.py  # TelegramClient (TDLib wrapper)
│   ├── telegram_message_service.py
│   ├── openai_chat.py      # OpenAIChat (LLM client)
│   ├── embedding_adapter.py # OpenAI embedding adapter
│   ├── memory/             # ✅ Memory infrastructure (ТЗ-002 hybrid: SQLite + ChromaDB)
│   │   ├── memory_service.py           # High-level API (dual-write ChromaDB + SQLite)
│   │   ├── memory_formation.py         # LLM-based automatic memory extraction
│   │   ├── storage.py                  # MemoryStore (ChromaDB wrapper)
│   │   ├── vector_store.py             # ChromaDB vector operations (HNSW ANN)
│   │   ├── memory_repository.py        # SQLite metadata storage
│   │   ├── memory_link_repository.py   # Entity relationships (SQLite)
│   │   ├── user_preference_repository.py # User preferences (SQLite)
│   │   ├── memory_tag_repository.py    # Memory tags (SQLite)
│   │   ├── conversation_repository.py  # Message history (SQLite)
│   │   ├── working_memory.py           # In-memory context + .md persistence
│   │   ├── database.py                 # SQLite schema & connection
│   │   ├── kuni_archive_reader.py      # Legacy C++ kuni format reader
│   │   ├── kuni_migrator.py            # Migration: C++ kuni → kunipy
│   │   └── memory_exporter.py          # Export to JSON/JSONL/Markdown
│   ├── delivery/           # ✅ Delivery tracking (ТЗ-001 complete)
│   │   ├── storage.py         # MessageDeliveryStorage (SQLite WAL)
│   │   ├── tracker.py         # MessageDeliveryTracker
│   │   └── telegram_checker.py # TelegramMessageDeliveryChecker
│   └── worker/
│       └── stub_notification_manager.py
│
├── di/                      # Dependency injection
│   ├── __init__.py
│   └── container.py        # Dependencies, create_dependencies()
│
├── tests/
│   ├── architecture/       # Architecture tests
│   │   ├── test_layer_boundaries.py
│   │   ├── test_no_god_objects.py
│   │   └── test_interface_compliance.py
│   └── ...
│
├── app.py                  # Composition root (thin)
├── config.py               # Configuration
├── diary.py                # Legacy memory (migrating to new system)
├── worker.py               # Worker implementation
└── tools.py                # LLM tools
```

---

## Core Concepts

### 1. Protocols (Interfaces)

All cross-layer dependencies use `typing.Protocol` for structural subtyping:

```python
from typing import Protocol

class IOpenAIChat(Protocol):
    async def chat(self, messages: List[Message], **kwargs) -> Response:
        ...
    
    async def embedding(self, text: str) -> List[float]:
        ...
```

**Benefits**:
- No inheritance required
- Duck typing with type safety
- Easy mocking for tests
- Implementation can be swapped

### 2. Dependency Injection

All components receive dependencies via constructor:

```python
@dataclass
class Dependencies:
    config: Config
    openai_chat: IOpenAIChat
    telegram_client: ITelegramClient
    memory_store: IMemoryStore
    # ... more dependencies

def create_dependencies(config: Config) -> Dependencies:
    """Wire all dependencies together."""
    openai_chat = OpenAIChat(...)
    telegram_client = TelegramClient(...)
    # ... create and wire
    return Dependencies(...)
```

**Usage**:
```python
# In main
deps = create_dependencies(config)
worker = Worker(deps)
```

### 3. Domain Models

Business models are independent of infrastructure:

```python
@dataclass
class TelegramMessage:
    """Domain representation (not TDLib wire format)."""
    message_id: int
    chat_id: int
    user_id: int
    text: str
    timestamp: datetime
    media: Optional[MediaInfo] = None
```

**Benefits**:
- Infrastructure can be replaced
- Business logic stays stable
- Easy to test
- Clear contracts

### 4. Application Services

Orchestrate business operations using domain models and interfaces:

```python
class TelegramEventHandler:
    def __init__(self, deps: Dependencies):
        self._deps = deps
    
    async def handle_new_message(self, message: TelegramMessage):
        # Use interfaces, not concrete implementations
        notification = self._create_notification(message)
        await self._deps.notification_manager.pass_notification(notification)
```

---

## Design Patterns

### Pattern 1: Init Struct (from C++ kuni)

**C++**:
```cpp
struct Init {
    APath diaryDir;
    _<IOpenAIChat> openAI;
};
Diary(Init init);
```

**Python**:
```python
@dataclass
class DiaryConfig:
    diary_dir: Path
    openai_chat: IOpenAIChat

class Diary:
    def __init__(self, config: DiaryConfig):
        self._config = config
```

### Pattern 2: NotificationManager with Worker Pins

Based on C++ `NotificationManager.h`:

```python
@dataclass
class Notification:
    message: str
    priority: int = 0
    pin: Optional[str] = None  # Worker affinity

class INotificationManager(Protocol):
    async def pass_notification(
        self,
        message: str,
        priority: int = 0,
        pin: Optional[str] = None
    ) -> NotificationHandle:
        ...
```

**Worker pins** ensure same chat routes to same worker (maintains context).

### Pattern 3: Confidence Model (from C++ Diary)

```python
@dataclass
class MemoryPiece:
    confidence: float  # -1 (lie) to 0 (theory) to 1 (ground truth)
    importance: float
    usage_count: int
    last_used: datetime
```

Sleep consolidation can:
- Merge duplicates
- Increase confidence on confirmation
- Decrease confidence on contradiction
- Remove low-confidence entries

### Pattern 4: Memory Scopes (ТЗ-002)

```python
class MemoryScope(Enum):
    PRIVATE = "private"    # Character internal
    USER = "user"          # Specific user
    CHAT = "chat"          # Specific chat
    SHARED = "shared"      # Cross-user with permission
    GLOBAL = "global"      # Character general knowledge
```

Memory retrieval respects scope boundaries.

---

## Multi-Level Memory Architecture (ТЗ-001/ТЗ-002)

### Memory Levels

1. **Conversation Memory**: Current dialog history
2. **Chat Memory**: Persistent chat context
3. **User Memory**: User-specific knowledge
4. **Personal Cross-Channel Memory**: Desktop ↔ Telegram linking
5. **Character/Global Memory**: General knowledge
6. **Working Memory**: Current interaction state

## Hybrid Memory Architecture (ТЗ-002)

### Design: SQLite + ChromaDB

Память kunipy построена на двух движках:

- **ChromaDB** — векторный поиск (HNSW ANN). Семантический retrieval по косинусному расстоянию, <100ms на объёмах <100K записей.
- **SQLite (WAL mode)** — метаданные, связи, теги, предпочтения, история переписок. Транзакции, реляционные запросы, `busy_timeout=5000`, `foreign_keys=ON`.

PostgreSQL не используется: нагрузка userbot'а (1–5 workers, разные chat_id) полностью покрывается
SQLite WAL, а весь PostgreSQL-код удалён как мёртвый.

### Memory Flow

```
Message
   ↓
WorkingMemory (in-memory + working_memory.md)  — promises, plans, questions
   ↓
ConversationRepository (SQLite)                — полная история сообщений
   ↓
MemoryFormationService (LLM extraction)        — факты, события, мысли
   ↓
MemoryService.create_memory() — dual-write:
   ├─→ MemoryStore (ChromaDB)   — embedding + searchable metadata
   └─→ MemoryRepository (SQLite)— metadata, links, tags, provenance
   ↓
retrieve_context() на следующем запросе (RAG через ChromaDB HNSW)
```

### MemoryService (`src/infrastructure/memory/memory_service.py`)

Центральный high-level API. Инкапсулирует dual-write и многоуровневый retrieval:

```python
class MemoryService:
    def __init__(
        self,
        memory_store: MemoryStore,                    # ChromaDB
        memory_repo: MemoryRepository,                # SQLite metadata
        memory_link_repo: MemoryLinkRepository,       # SQLite links (§35)
        user_preference_repo: UserPreferenceRepository,  # SQLite prefs (§7.3)
        memory_tag_repo: MemoryTagRepository,         # SQLite tags (§9)
        conversation_repo: ConversationRepository,    # SQLite history (§20)
        user_repo: UserRepository,
        chat_repo: ChatRepository,
        working_memory: WorkingMemory,                # in-memory + .md
        embedding_provider: IEmbeddingProvider,
        config: Config,
    ): ...

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Dual-write: ChromaDB (vectors) → SQLite (metadata)."""
        await self.memory_store.create_memory(piece)
        await self.memory_repo.create_memory(piece)
        return piece.id

    async def retrieve_context(self, user_id, chat_id, channel, query_text,
                               max_pieces=10):
        """Multi-level retrieval via ChromaDB HNSW + WorkingMemory."""
        ...
```

**Retrieval strategy** (`retrieve_context`):
1. Working memory context (promises/plans/questions)
2. Query embedding через embedding provider
3. Многоуровневый поиск через ChromaDB HNSW: CHAT (3) → USER (3, cross-channel) → PRIVATE (2, desktop owner) → GLOBAL (2)
4. Дедупликация по id, ранжирование по similarity
5. Топ-N в system prompt

### SQLite Repository Layer

Все репозитории работают на одном WAL-соединении (`database.py` — схема и подключение):

| Репозиторий | Таблица | Назначение |
|-------------|---------|-----------|
| `MemoryRepository` | `memory_pieces`, `memory_embeddings` | Метаданные воспоминаний; embedding BLOB (backup/recovery) |
| `ConversationRepository` | `conversation_messages` | История сообщений с provenance (§20) |
| `MemoryLinkRepository` | `memory_links` | Связи между сущностями (§35) |
| `UserPreferenceRepository` | `user_preferences` | Предпочтения пользователей (§7.3) |
| `MemoryTagRepository` | `memory_tags` | Теги воспоминаний (§9) |
| `UserRepository` / `ChatRepository` | `users`, `chats` | Профили и чаты |

### ChromaDB Layer

- `VectorStore` (`vector_store.py`) — низкоуровневая обёртка коллекции ChromaDB: `add_memory`,
  `update_memory` (merge metadata — ChromaDB заменяет dict целиком, поэтому читаем старые поля
  и мержим), `search` (HNSW ANN), `count(where=...)`.
- `MemoryStore` (`storage.py`) — реализация `IMemoryStore`: конвертация `MemoryPiece` ↔ документ,
  списки (`source_message_ids`, `retrieval_cues`, `entities`, `metadata`) сериализуются в JSON
  внутри ChromaDB metadata. Обновление usage-статистики — батчем, не по одному разу на результат.

### WorkingMemory (`working_memory.py`)

Единая реализация короткой памяти: dict в памяти + персист в `working_memory.md`
(через `WorkingMemoryFileStore`). Человекочитаемый файл удобен для отладки.
Дублирующий SQL-репозиторий `working_memory_repository.py` удалён.

### Memory Formation (`memory_formation.py`)

`MemoryFormationService` периодически (каждые N сообщений) вызывает LLM для извлечения
фактов/событий/мыслей из диалога, создаёт `MemoryPiece` с scope и confidence, сохраняет
через `MemoryService.create_memory()` (т.е. тоже dual-write).

### DI Container Integration

```python
# src/di/container.py (memory_enabled)
memory_db = MemoryDatabase(working_dir / config.memory_db_path)
sqlite_conn = memory_db.connect()
sqlite_conn.execute("PRAGMA journal_mode=WAL")
sqlite_conn.execute("PRAGMA busy_timeout=5000")
memory_db.initialize_schema()

memory_store = MemoryStore(persist_directory=str(working_dir / "chroma"))
working_memory = WorkingMemory(file_store=WorkingMemoryFileStore(working_dir / "working_memory.md"))

memory_service = MemoryService(
    memory_store=memory_store,
    memory_repo=MemoryRepository(sqlite_conn, embedding_model=...),
    memory_link_repo=..., user_preference_repo=..., memory_tag_repo=...,
    conversation_repo=..., user_repo=..., chat_repo=...,
    working_memory=working_memory,
    embedding_provider=embedding_provider,
    config=config,
)
```

### Migration from C++ kuni

CLI-инструмент: **`migrate_kuni.py`** (в корне проекта). `KuniMigrator` пишет через
`MemoryService`, поэтому миграция наполняет оба хранилища сразу:

```bash
python migrate_kuni.py --kuni-dir /path/to/cpp-kuni/diary --dry-run
python migrate_kuni.py --kuni-dir /path/to/cpp-kuni/diary --scope global
```

Сохраняются embeddings (переиспользование из архива), confidence, usage_count; проставляется
provenance `source_type="migration"`.

Подробности — в [docs/MIGRATION.md](MIGRATION.md).

---

## Telegram Delivery Tracking (ТЗ-001 punkt 12-18)

### State Machine

```
PENDING → SENT → DELIVERED (within 10s)
            ↓
         RETRY_PENDING (after 10s timeout)
            ↓
         SENT → DELIVERED
            ↓
         FAILED (after max retries)
```

### 10-Second Rule

From ТЗ-001 punkt 13:
- Message sent → start timer
- Check delivery within 10 seconds
- If delivered: mark DELIVERED
- If timeout: mark RETRY_PENDING

### Duplicate Detection

From ТЗ-001 punkt 18:
- Hash message text
- Check if sent to same chat in last 60s
- Prevent duplicate sends

### Implementation Status

- **Phase 1**: Interfaces + domain models ✅
- **Phase 2**: Full implementation with verification

---

## Testing Strategy

### Architecture Tests

Enforce architectural rules:

```python
def test_domain_does_not_import_infrastructure():
    """Domain layer must not depend on infrastructure."""
    # Scan domain/ for forbidden imports
    assert no_violations
```

**Test Suites**:
1. `test_layer_boundaries.py` - Dependency rules
2. `test_no_god_objects.py` - SRP violations
3. `test_interface_compliance.py` - Protocol compliance

### Unit Tests

Mock all dependencies via protocols:

```python
class MockOpenAIChat:
    async def chat(self, messages, **kwargs):
        return Response(content="mocked", ...)

def test_worker():
    deps = create_mock_dependencies()
    worker = Worker(deps)
    # Test worker logic
```

### Integration Tests

Test dependency wiring:

```python
def test_dependency_container():
    config = Config.load()
    deps = create_dependencies(config)
    assert deps.openai_chat is not None
    assert isinstance(deps.telegram_client, TelegramClient)
```

---

## Migration Guide

### From Singleton to DI

**Before**:
```python
class Worker:
    def __init__(self):
        self._config = get_config()  # Singleton!
        self._openai = get_openai()  # Singleton!
```

**After**:
```python
class Worker:
    def __init__(self, deps: Dependencies):
        self._deps = deps
        # Use deps.config, deps.openai_chat
```

### From God Object to Focused Classes

**Before** (app.py - 727 lines, 11+ responsibilities):
```python
class App:
    def handle_telegram_event(self): ...
    def manage_workers(self): ...
    def schedule_sleep(self): ...
    def send_proactive_messages(self): ...
    # ... 7 more responsibilities
```

**After** (5 focused classes):
```python
class TelegramEventHandler:
    async def handle_new_message(self, message): ...

class WorkerOrchestrator:
    async def start_workers(self, count): ...

class SleepScheduler:
    async def schedule_next_sleep(self): ...

# ... etc
```

---

## Best Practices

### DO ✅

1. **Use protocols for all interfaces**
   ```python
   class IService(Protocol):
       async def do_something(self) -> Result: ...
   ```

2. **Inject dependencies via constructor**
   ```python
   def __init__(self, deps: Dependencies):
       self._deps = deps
   ```

3. **Keep domain models pure**
   ```python
   @dataclass
   class DomainModel:
       # No framework dependencies
       # No infrastructure imports
   ```

4. **Test architecture rules**
   ```python
   def test_no_god_objects():
       assert all_classes_under_300_lines()
   ```

### DON'T ❌

1. **Don't use singletons**
   ```python
   # ❌ Bad
   config = get_config()
   
   # ✅ Good  
   def __init__(self, config: Config):
       self._config = config
   ```

2. **Don't mix layers**
   ```python
   # ❌ Bad: Domain importing infrastructure
   from infrastructure.telegram_client import TelegramClient
   
   # ✅ Good: Domain using protocol
   from interfaces.telegram import ITelegramClient
   ```

3. **Don't create god objects**
   ```python
   # ❌ Bad: 727 lines, 11+ responsibilities
   class App:
       # Everything in one class
   
   # ✅ Good: Focused classes
   class TelegramEventHandler:
       # One responsibility
   ```

---

## FAQ

### Q: Why protocols instead of abstract base classes?

**A**: Protocols provide structural subtyping (duck typing with type safety). No inheritance required, easier mocking, more Pythonic.

### Q: Why so many layers?

**A**: Clear boundaries prevent spaghetti code. Each layer has one job:
- **Domain**: Business rules
- **Interfaces**: Contracts
- **Application**: Orchestration  
- **Infrastructure**: External systems

### Q: When to use stubs vs full implementation?

**A**: 
- **Phase 1**: Stubs for architecture (interfaces complete)
- **Phase 2+**: Replace stubs with real implementations
- Stubs allow system to compile while deferring implementation

### Q: How to add new feature?

**A**:
1. Define protocol in `interfaces/`
2. Add to `Dependencies` dataclass
3. Create stub implementation
4. Wire in `create_dependencies()`
5. Implement for real in future phase

### Q: How does this relate to C++ kuni?

**A**: Replicates proven patterns:
- DI via Init structs → Config dataclasses
- IOpenAIChat interface → Protocol
- NotificationManager → Worker pins
- Diary confidence model → MemoryPiece
- Layer separation → Clean architecture

---

## Autonomy Features

### Working Memory Extraction

**Purpose**: Extract short-term context (promises, tasks, emotional state) after conversation sessions.

**Flow**:
1. User conversation ends (before sleep or context clear)
2. `WorkingMemoryUpdateService.update_after_session()` called
3. LLM extracts structured memory using `prompts/important_things_to_remember.md`
4. Parsed sections update `WorkingMemory` storage
5. Persisted to `.md` file for next session

**Sections extracted**:
- Promises made
- Unfinished tasks
- Pending questions
- Emotional state
- Physical state
- Important context

**Integration**: Called from `Worker._process_notification()` after LLM response, before sleep.

### Autonomous Diary Saving

**Purpose**: Automatically save conversation summaries to diary after sessions (optional).

**Flow**:
1. If `auto_save_after_session = true` in config
2. `Worker._auto_save_diary()` called after working memory update
3. `DiaryDumpService._summarize_for_diary()` extracts meaningful entries
4. Each entry saved to `Diary` with confidence 0.7

**When**: After every conversation session, before sleep.

### Random Sleep Behavior

**Purpose**: Human-like fatigue - character may randomly decide to sleep after processing.

**Flow**:
1. After message processing completes
2. If `random_sleep_enabled = true` in config
3. 30% probability: `Worker._schedule_sleep()` called
4. Character goes to sleep, performs memory consolidation
5. Wakes up after configured `sleep_timeout`

**Integration**: Implemented in `Worker._process_notification()` after response generation.

---

## References

- **ТЗ-001**: [D:\AI\Техзадания\ТЗ-001 Техническое задание - основа.txt](D:\AI\Техзадания\ТЗ-001 Техническое задание - основа.txt)
- **ТЗ-002**: Memory system specification
- **ТЗ-003**: Telegram vision specification
- **C++ kuni**: [D:\AI\kuni-cpp\](D:\AI\kuni-cpp\)
- **Phase 0 Audit**: [D:\AI\AUDIT_REPORT_TZ001.md](D:\AI\AUDIT_REPORT_TZ001.md)
- **Phase 1 Plan**: [D:\AI\PHASE1_PLAN.md](D:\AI\PHASE1_PLAN.md)

---

## Next Steps

Актуальное состояние — в [CURRENT_STATE.md](../CURRENT_STATE.md).
