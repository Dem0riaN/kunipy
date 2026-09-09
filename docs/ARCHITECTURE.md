# kunipy Architecture Guide

**Version**: Phase 1  
**Last Updated**: 2026-09-09

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
│  - MemoryStore (Database)               │
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
│   ├── memory/
│   │   └── stub_store.py   # InMemoryStore (Phase 2: real DB)
│   ├── delivery/
│   │   └── stub_tracker.py # StubDeliveryTracker (Phase 2: real)
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

## Multi-Level Memory Architecture (ТЗ-002)

### Memory Levels

1. **Conversation Memory**: Current dialog history
2. **Chat Memory**: Persistent chat context
3. **User Memory**: User-specific knowledge
4. **Personal Cross-Channel Memory**: Desktop ↔ Telegram linking
5. **Character/Global Memory**: General knowledge
6. **Working Memory**: Current interaction state

### Memory Flow

```
Message
   ↓
Working Memory (current state)
   ↓
Conversation History
   ↓
Sleep Consolidation
   ↓
Long-Term Memory (scope-specific)
   ↓
RAG Retrieval (on next query)
```

### Implementation Status

- **Phase 1**: Interfaces + domain models ✅
- **Phase 2**: Full implementation with vector DB
- **Phase 3**: Multi-channel context switching

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

## References

- **ТЗ-001**: [D:\AI\Техзадания\ТЗ-001 Техническое задание - основа.txt](D:\AI\Техзадания\ТЗ-001 Техническое задание - основа.txt)
- **ТЗ-002**: Memory system specification
- **ТЗ-003**: Telegram vision specification
- **C++ kuni**: [D:\AI\kuni-cpp\](D:\AI\kuni-cpp\)
- **Phase 0 Audit**: [D:\AI\AUDIT_REPORT_TZ001.md](D:\AI\AUDIT_REPORT_TZ001.md)
- **Phase 1 Plan**: [D:\AI\PHASE1_PLAN.md](D:\AI\PHASE1_PLAN.md)

---

## Next Steps

See [PHASE1_PROGRESS.md](D:\AI\PHASE1_PROGRESS.md) for current status and remaining tasks.
