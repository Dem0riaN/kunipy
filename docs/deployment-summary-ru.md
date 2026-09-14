# Руководство по развёртыванию системы памяти (kunipy)

**Дата:** 2026-09-13
**Проект:** kunipy
**Спецификация:** ТЗ-002 Техническое задание — память
**Версия:** 0.5.0 (Гибридная архитектура: SQLite WAL + ChromaDB HNSW)

> Обновлённое руководство. Предыдущая версия (2026-09-11) описывала только SQLite
> с numpy-kNN поиском — этот документ заменён и описывает финальную гибридную архитектуру.

---

## Резюме архитектуры

kunipy — многоканальный AI-персонаж (Telegram/desktop/voice) с гибридной системой памяти:

```
MemoryService (high-level API, dual-write)
├── MemoryStore (ChromaDB)              — векторный поиск (HNSW ANN)
├── MemoryRepository (SQLite)           — метаданные воспоминаний
├── MemoryLinkRepository (SQLite)       — связи сущностей (§35)
├── UserPreferenceRepository (SQLite)   — предпочтения (§7.3)
├── MemoryTagRepository (SQLite)        — теги (§9)
├── ConversationRepository (SQLite)     — история сообщений (§20)
├── UserRepository / ChatRepository     — профили и чаты
├── WorkingMemory (in-memory + .md)     — promises, plans, questions
└── MemoryFormationService              — LLM-экстракция воспоминаний
```

**Dual-write:** `MemoryService.create_memory()` пишет вектор в ChromaDB, затем метаданные
в SQLite. Это обеспечивает и быстрый семантический поиск (<100ms), и полноценные транзакции.

**Почему SQLite, а не PostgreSQL:**
Нагрузка userbot'а (1-5 workers, разные chat_id, ~10 writes/sec) полностью покрывается
SQLite с WAL mode + `busy_timeout=5000`. Весь PostgreSQL-код удалён как мёртвый.

---

## Структура директорий

```
G:\AI\kunipy-main                → Исходный код (Windows, только синхронизация)
/home/alexey/kunipy              → Развертывание (WSL Ubuntu-24.04, рабочая копия)
```

### Директории данных

```
kunipy/
├── data/
│   ├── memory.db                 # SQLite метаданные (WAL mode)
│   ├── chroma/                   # ChromaDB векторный индекс памяти
│   │   ├── chroma.sqlite3
│   │   └── ... (HNSW индексы)
│   ├── working_memory.md         # WorkingMemory persistence
│   ├── delivery.db               # Delivery tracking
│   └── tdlib/                    # Telegram session (если enabled)
├── config.toml                   # Конфигурация
└── ...
```

---

## Развертывание

### 1. Копирование файлов

```bash
# Из Windows в WSL (из G:\AI\kunipy-main в /home/alexey/kunipy)
cp -r /mnt/g/AI/kunipy-main/* /home/alexey/kunipy/
```

### 2. Виртуальное окружение

```bash
cd /home/alexey/kunipy
source .venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Конфигурация

```bash
# Создать config.toml из примера
cp config.example.toml config.toml
```

**Секция `[memory]` в config.toml:**

```toml
[memory]
# kunipy использует гибридную архитектуру памяти:
# - SQLite для метаданных, ссылок, тегов, preferences
# - ChromaDB для векторного поиска (HNSW ANN)

enabled = true                    # Включить систему памяти
db_path = "data/memory.db"        # Путь к SQLite базе
min_similarity = 0.5              # Порог векторного поиска (0.0-1.0)
# desktop_owner_telegram_id = "123456789"  # Опционально
```

**Устаревшие ключи (удалены из config.py):**
- ~~`memory_backend = "postgresql"`~~
- ~~`memory_postgres_url`~~

### 4. Запуск

```bash
python run.py
```

При первом запуске система автоматически:
- Создаст SQLite базу `data/memory.db`
- Создаст ChromaDB индекс в `data/chroma/`
- Создаст файл `data/working_memory.md`
- Инициализирует все таблицы и индексы

---

## Тестирование

### Минимальный тест (репозитории SQLite)

Обходит TDLib, тестирует только слой памяти:

```bash
python test_memory_minimal.py
```

**Ожидаемый результат:**
```
✅ All memory system components working correctly!
```

### Интеграционный тест (полный поток)

Тестирует MemoryService с ChromaDB + SQLite (dual-write):

```bash
python test_memory_integration.py
```

**Ожидаемый результат:**
```
✅ Integration test completed successfully!
Summary:
  - Messages stored: 4
  - Promises tracked: 1
  - Database: data/test_integration.db
```

### Тест Memory Formation

```bash
python test_memory_formation.py
```

### Тест Worker интеграции

```bash
python test_memory_worker_integration.py
```

---

## Верификация гибридной архитектуры

### 1. Проверка SQLite схемы

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/memory.db')
cursor = conn.cursor()
for table in ['memory_pieces', 'memory_links', 'user_preferences', 'memory_tags', 'conversation_messages']:
    cursor.execute(f\"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'\")
    assert cursor.fetchone() is not None, f'{table} missing'
print('✅ SQLite schema OK')
"
```

### 2. Проверка ChromaDB

```bash
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='data/chroma')
collection = client.get_or_create_collection('memories')
print(f'ChromaDB collection: {collection.count()} vectors')
print('✅ ChromaDB OK')
"
```

### 3. Проверка dual-write

```bash
python3 -c "
import asyncio
from src.config import load_config
from src.di.container import create_dependencies
from pathlib import Path

async def test():
    config = load_config('config.toml')
    deps = await create_dependencies(Path('data'), config)
    assert deps.memory_service is not None
    assert deps.memory_service.memory_store is not None   # ChromaDB
    assert deps.memory_service.memory_repo is not None    # SQLite
    print('✅ DI + dual-write OK')

asyncio.run(test())
"
```

### 4. Проверка миграции

```bash
python migrate_kuni.py --kuni-dir ./old_diary --stats
python migrate_kuni.py --kuni-dir ./old_diary --dry-run
```

---

## Известные проблемы

### TDLib Segfault (Exit Code 139)

**Статус:** Известная проблема, отложена по решению владельца.

TDLib может падать при полном DI-запуске. **Workaround:** тесты репозиториев обходят TDLib и работают корректно.

> "Ошибку TDLib игнорировать — проблема известная, отложена в долгий ящик"

### Windows: нет Python интерпретатора

Windows-копия в `G:\AI\kunipy-main` — только исходники для синхронизации.
Все тесты и запуск — в WSL Ubuntu-24.04.

---

## Производительность

| Операция | Время | Комментарий |
|----------|-------|-------------|
| Векторный поиск (ChromaDB HNSW) | 10-50ms | <100K записей |
| Multi-level retrieval | ~100-200ms | 4 уровня (CHAT→USER→PRIVATE→GLOBAL) |
| SQLite INSERT | ~1ms | WAL mode, busy_timeout=5000 |
| Memory formation (LLM) | ~1-2 sec | Каждые 6 сообщений |
| Хранение на воспоминание | ~17KB | 1KB метаданные + 16KB embedding (4096-dim) |

---

## Созданные/модифицированные файлы

### Созданные (гибридная архитектура)

```
src/infrastructure/memory/
  ├── memory_service.py              # High-level API (dual-write)
  ├── memory_formation.py            # LLM-экстракция воспоминаний
  ├── storage.py                     # MemoryStore (ChromaDB wrapper)
  ├── vector_store.py                # ChromaDB HNSW операции
  ├── memory_repository.py           # SQLite метаданные
  ├── memory_link_repository.py      # Связи (§35)
  ├── user_preference_repository.py  # Предпочтения (§7.3)
  ├── memory_tag_repository.py       # Теги (§9)
  ├── conversation_repository.py     # История сообщений (§20)
  ├── working_memory.py              # In-memory + .md persistence
  ├── working_memory_file_store.py   # .md persistence backend
  ├── database.py                    # SQLite schema (WAL)
  ├── kuni_archive_reader.py         # C++ kuni формат reader
  ├── kuni_migrator.py               # C++ kuni → kunipy миграция
  └── memory_exporter.py             # JSON/JSONL/Markdown экспорт
src/domain/memory_models.py          # Domain entities
test_memory_minimal.py               # Repository layer tests
test_memory_integration.py           # Full flow integration tests
migrate_kuni.py                      # CLI migration tool
export_memory.py                     # CLI export tool
docs/ARCHITECTURE.md                 # Детальная архитектура
docs/MIGRATION.md                    # Руководство по миграции
docs/FINAL_REPORT.md                 # Финальный отчёт
docs/deployment-summary-ru.md        # Этот файл
```

### Модифицированные

```
src/config.py                        # SQLite-only keys (удалены postgres keys)
src/di/container.py                  # Wired MemoryService + 7 repos + ChromaDB
src/application/telegram_handler.py  # Store incoming messages
src/worker.py                        # Inject memory_service
src/app.py                           # Pass memory_service to workers
```

### Удалённые (мёртвый код)

```
postgres_database.py                 # PostgreSQL schema (никогда не деплоилась)
postgres_adapter.py                  # PostgreSQL адаптер
async_postgres_adapter.py            # Async PostgreSQL
async_postgres_connection.py         # Async PG connection
universal_db_adapter.py              # SQL-абстракция
working_memory_repository.py         # Дублировал WorkingMemory (in-memory + .md)
working_memory_extractor.py          # Не использовался
migrate_to_postgres.py               # PostgreSQL migration tool
```

---

## Соответствие ТЗ-002

| Пункт ТЗ | Статус | Реализация |
|----------|--------|------------|
| 4. User/Chat разделение | ✅ | UserRepository, ChatRepository |
| 7. Три слоя памяти | ✅ | Conversations → Memories → WorkingMemory |
| 9-14. MemoryPiece модель | ✅ | ChromaDB vectors + SQLite metadata |
| 15-19. MemoryScope | ✅ | PRIVATE, USER, CHAT, SHARED, GLOBAL |
| 20-22. Conversation history | ✅ | ConversationRepository (§20) |
| 23-26. Embeddings | ✅ | ChromaDB HNSW (не numpy kNN) |
| 25. Hybrid storage | ✅ | SQLite WAL + ChromaDB |
| 26. Pluggable storage | ✅ | IMemoryStore protocol |
| 27-31. RetrievalContext | ✅ | Multi-level HNSW search |
| 32-33. Desktop owner | ✅ | config.desktop_owner_telegram_id |
| 34-37. Working memory | ✅ | In-memory + .md persistence |
| 35. Entity relationships | ✅ | memory_links + MemoryLinkRepository |
| 7.3. User preferences | ✅ | user_preferences + репозиторий |
| 9. Memory tags | ✅ | memory_tags + репозиторий |
| 38-42. API операции | ✅ | MemoryService dual-write API |
| 43-45. Многоканальность | ✅ | telegram/desktop/voice |
| Migration | ✅ | KuniMigrator → MemoryService |
| Consolidation | ⏳ | Следующая итерация |

---

## Дальнейшие шаги

1. **Консолидация памяти** — merge/summarize старых воспоминаний
2. **Граф сущностей** — использование memory_links в retrieval
3. **Диагностические инструменты** — проверка консистентности ChromaDB↔SQLite
4. **Расширенные тесты** — round-trip сериализации, scope visibility

---

**Обновлено:** 2026-09-12
**Версия:** 0.4.0 (Гибридная архитектура: SQLite WAL + ChromaDB HNSW)
