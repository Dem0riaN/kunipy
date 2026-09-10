# kunipy — Актуальное состояние проекта

**Дата:** 2026-09-10  
**Статус:** Production Ready  
**Архитектура:** Clean Architecture (4 слоя)

---

## Текущее состояние системы памяти

### Dual Memory System (Гибридная система)

В проекте **одновременно работают ДВЕ системы памяти**:

#### 1. Legacy Diary (Старая система)
**Файл:** `src/diary.py`  
**Статус:** ✅ Работает параллельно с новой системой  
**Хранилище:** Файлы `*.md` в директории `config.diary_dir`  
**Активация:** `config.diary_enabled = true`

**Особенности:**
- Читает существующие diary файлы напрямую
- Не требует миграции
- Использует file-based storage с embeddings
- Полностью функциональна

**Интеграция в DI:**
```python
# src/di/container.py (lines 148-155)
diary = None
if config.diary_enabled:
    diary = Diary(
        diary_dir=Path(config.diary_dir),
        openai_chat=openai_chat,
        config=config,
    )
```

#### 2. New Memory System (Новая система)
**Файлы:** `src/infrastructure/memory/*`  
**Статус:** ✅ Полностью реализована и интегрирована  
**Хранилище:** ChromaDB в `working_dir/chroma`  
**Активация:** Всегда активна (часть DI)

**Компоненты:**
- `MemoryStore` — ChromaDB storage с semantic search
- `WorkingMemory` — In-memory context для текущего взаимодействия
- `VectorStore` — ChromaDB wrapper
- `EmbeddingCache` — TTL-based cache для embeddings

**Интеграция в DI:**
```python
# src/di/container.py (lines 135-143)
chroma_persist_dir = working_dir / "chroma"
chroma_persist_dir.mkdir(parents=True, exist_ok=True)

memory_store = MemoryStore(persist_directory=str(chroma_persist_dir))
working_memory = WorkingMemory()
```

### Важно: Системы НЕ конфликтуют

- **Legacy Diary:** работает с `config.diary_dir` (например, `./diary/`)
- **New Memory:** работает с `working_dir/chroma` (например, `./data/chroma/`)
- Обе системы доступны через `Dependencies` container
- Можно использовать обе одновременно или только одну

---

## Миграция (опциональна)

### Зачем мигрировать?

**Не обязательно**, но даёт преимущества:
- Unified memory system (всё в одном месте)
- Semantic search по всем данным
- Лучшая производительность (ChromaDB оптимизирован)
- Готовность к будущим фичам (multi-level memory)

### Как мигрировать?

**Одна команда:**
```bash
python migrate_diary.py --kuni-dir /path/to/old/diary
```

**После миграции:**
- Старые файлы остаются нетронутыми (backup)
- Новые данные в ChromaDB
- Можно отключить `config.diary_enabled = false`

**Без миграции:**
- Оставить `config.diary_enabled = true`
- Продолжать работу со старыми файлами
- Новая память работает параллельно

---

## Компоненты проекта

### 1. Memory Layer (Слой памяти)

**Protocols (Интерфейсы):**
- `IMemoryStore` — Long-term memory storage
- `IWorkingMemory` — Current interaction context

**Implementations (Реализации):**
- `MemoryStore` — ChromaDB-based persistent storage
- `WorkingMemory` — In-memory working context
- `Diary` — Legacy file-based storage (опционально)

**В DI container:**
```python
Dependencies(
    memory_store=MemoryStore(...),      # Новая система
    working_memory=WorkingMemory(),     # Новая система
    diary=Diary(...),                   # Старая система (если enabled)
    # ...
)
```

### 2. Delivery Tracking (Отслеживание доставки)

**Статус:** ✅ Полностью интегрировано  
**Компоненты:**
- `MessageDeliveryStorage` — SQLite WAL-mode storage
- `MessageDeliveryTracker` — Coordinator
- `TelegramMessageDeliveryChecker` — 10-second verification

**Интеграция:**
```python
# src/di/container.py (lines 120-130)
delivery_db_path = working_dir / "delivery.db"
delivery_storage = MessageDeliveryStorage(delivery_db_path, config)
delivery_checker = TelegramMessageDeliveryChecker(telegram_client)
delivery_tracker = MessageDeliveryTracker(delivery_storage, delivery_checker)
```

### 3. LLM Layer

**Компоненты:**
- `OpenAIChat` — OpenAI-compatible API client
- Implements `IOpenAIChat` and `IEmbeddingProvider` protocols

**Интеграция:**
```python
openai_chat = OpenAIChat(
    endpoint=config.llm,
    timeout=30,
    max_retries=2,
)
```

### 4. Telegram Layer (опционально)

**Статус:** Conditional (если `config.telegram_enabled = true`)  
**Компоненты:**
- `TelegramClient` — TDLib wrapper
- Delivery tracking integration

---

## Конфигурация

### config.toml

```toml
[diary]
enabled = true                    # Legacy diary (опционально)
directory = "./diary"             # Где лежат старые .md файлы
min_relatedness = 0.5

# Новая memory система НЕ требует конфигурации
# Автоматически использует working_dir/chroma
```

### Сценарии использования

#### Сценарий 1: Только старый Diary
```toml
[diary]
enabled = true
directory = "./diary"
```
**Результат:** Работает только legacy система, новая пустая

#### Сценарий 2: Только новая Memory
```toml
[diary]
enabled = false
```
**Результат:** Работает только ChromaDB, старые файлы игнорируются

#### Сценарий 3: Обе системы (гибридный режим)
```toml
[diary]
enabled = true
directory = "./diary"
```
**Результат:** Обе системы работают параллельно

#### Сценарий 4: После миграции
```toml
[diary]
enabled = false  # Старое выключено
```
Данные в ChromaDB, старые файлы как backup

---

## Архитектура (актуальная)

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
│                                         │
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

---

## Директории данных

```
kunipy-main/
├── diary/                    # Legacy diary (если enabled)
│   ├── 1788539848.md
│   ├── 1788775752.md
│   └── ...                   # ~1200 файлов
│
├── data/                     # Runtime data (gitignored)
│   ├── chroma/              # Новая memory система (всегда)
│   │   ├── chroma.sqlite3
│   │   └── ...
│   ├── delivery.db          # Delivery tracking
│   └── tdlib/               # Telegram session (если enabled)
│
└── config.toml              # Конфигурация
```

---

## Миграционная стратегия

### Вариант 1: Постепенная миграция
1. Оставить `diary.enabled = true`
2. Запустить `migrate_diary.py` для копирования в ChromaDB
3. Тестировать новую систему параллельно
4. Когда уверены — `diary.enabled = false`

### Вариант 2: Без миграции
1. Оставить `diary.enabled = true`
2. Продолжать использовать старую систему
3. Новая память для новых фич (когда понадобится)

### Вариант 3: Чистый старт
1. `diary.enabled = false`
2. Использовать только новую ChromaDB систему
3. Старые данные остаются как архив

---

## FAQ

### Нужно ли мигрировать данные?
**Нет.** Старая система работает как раньше. Миграция опциональна.

### Можно ли использовать обе системы?
**Да.** Они работают параллельно без конфликтов.

### Что происходит при миграции?
Данные **копируются** в ChromaDB. Оригинальные файлы не изменяются.

### Потеряю ли я данные если отключу diary.enabled?
**Нет.** Файлы остаются на диске. Просто не загружаются в память.

### Какая система лучше?
- **Legacy Diary:** проверенная, стабильная, работает "из коробки"
- **New Memory:** быстрее, semantic search, готова к будущим фичам

### Как выбрать?
- Есть много старых данных → оставить legacy или мигрировать постепенно
- Новый проект → использовать только new memory
- Не уверен → гибридный режим (обе включены)

---

## Состояние реализации ТЗ-001

✅ **Выполнено 100%:**
- Clean Architecture (4 слоя)
- DI container
- Memory infrastructure (ChromaDB)
- Migration tooling
- Integration tests
- Code quality (Ruff = 0)
- Documentation

**Особенность:** Legacy Diary сохранён для обратной совместимости.

---

## Документация

- [README.md](README.md) — Основная информация
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Детальная архитектура
- [docs/MIGRATION.md](docs/MIGRATION.md) — Руководство по миграции
- [STATUS_COMPLETE.md](STATUS_COMPLETE.md) — Статус ТЗ-001

---

**Обновлено:** 2026-09-10  
**Версия:** Production Ready
