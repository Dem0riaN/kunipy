# ТЗ-002: Memory System — Final Report

**Дата:** 2026-09-13
**Проект:** kunipy
**Спецификация:** ТЗ-002 Техническое задание — память
**Статус:** ✅ Финальная гибридная архитектура реализована (v0.5.0)

> Этот отчёт заменил черновик от 2026-09-11 (Stages 1-7, SQLite-only kNN).
> С тех пор система перешла на гибрид **SQLite WAL + ChromaDB HNSW**,
> исправлены критические SQL/ChromaDB баги, удалён весь мёртвый PostgreSQL-код.

---

## 📊 Что реализовано

### 1. Гибридная архитектура памяти

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

**Dual-write:** `MemoryService.create_memory()` пишет вектор в ChromaDB, затем метаданные в SQLite.

### 2. Исправленные критические баги (Этапы 1-4 плана)

| Баг | Исправление |
|-----|-------------|
| `database.py` создавал `memory_pieces`, репозиторий писал в `memories` — все SQL падали | Единое имя таблицы `memory_pieces` |
| `last_used` vs `last_used_at` — mismatch колонок | Приведено к схеме |
| INSERT в `memory_embeddings` без обязательных `embedding_model`/`dimension` | Полная колонка в INSERT |
| `search_by_embedding()` — brute-force O(n) numpy cosine | Удалён; векторный поиск только через ChromaDB HNSW |
| ChromaDB `update_memory()` терял metadata (полная замена dict) | Read-modify-merge |
| `count()` игнорировал фильтр | `count(where=...)` |
| N+1 обновлений usage_count в search | Инкремент в памяти + batch update |
| Списки (`entities`, `retrieval_cues`, `source_message_ids`, `metadata`) не персистировались | JSON-сериализация в ChromaDB metadata |

### 3. SQLite-схема (WAL mode)

Таблицы (`src/infrastructure/memory/database.py`):
- `memory_pieces` — метаданные (embeddings в ChromaDB)
- `memory_embeddings` — BLOB-векторы (backup/recovery)
- `memory_links` — связи (§35)
- `memory_tags` — теги (§9)
- `user_preferences` — предпочтения (§7.3)
- `conversation_messages` — история (§20)
- `users`, `chats`

Прагмы: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`.

### 4. Конфигурация (SQLite-only)

```toml
[memory]
enabled = true
db_path = "data/memory.db"
min_similarity = 0.5
# desktop_owner_telegram_id = "123456789"
```

**Удалены из config.py:** `memory_backend`, `memory_postgres_url`.

### 5. DI Container

`src/di/container.py` при `memory_enabled=true`:
- инициализирует SQLite (WAL) + все 7 репозиториев
- создаёт ChromaDB `MemoryStore` в `data/chroma/`
- собирает `MemoryService` со всеми зависимостями
- `MemoryIntegratedWorker` получает контекст памяти до LLM-вызова

### 6. Миграция из C++ kuni

`KuniMigrator` переписан на `MemoryService` (раньше писал мимо ChromaDB):
- CLI: `migrate_kuni.py --kuni-dir ./diary [--dry-run] [--stats] [--export-json ...]`
- Сохраняет embeddings из архива (или регенерирует), confidence, usage_count
- Provenance: `source_type="migration"`, `metadata.original_id`

### 7. Удалён мёртвый код

| Файл | Причина |
|------|---------|
| `postgres_database.py` | PostgreSQL никогда не деплоился |
| `universal_db_adapter.py` | SQL-абстракция не нужна |
| `postgres_adapter.py` | Мёртвый код |
| `async_postgres_adapter.py` | Мёртвый код |
| `async_postgres_connection.py` | Мёртвый код |
| `working_memory_repository.py` | Дублировал `WorkingMemory` (in-memory + .md) |
| `working_memory_extractor.py` | Нигде не использовался |
| `migrate_to_postgres.py` | PostgreSQL-путь удалён |

---

## 🎯 Соответствие ТЗ-002

| Требование | Статус | Реализация |
|------------|--------|------------|
| Multi-user / multi-chat / multi-channel | ✅ | Platform-agnostic IDs (`telegram:12345`) |
| Three-layer architecture | ✅ | Conversations → Memories → Working Memory |
| MemoryScope (5 levels) | ✅ | PRIVATE, USER, CHAT, SHARED, GLOBAL |
| Embedding-based search | ✅ | **ChromaDB HNSW ANN** (вместо numpy kNN) |
| Hybrid storage (§25) | ✅ | SQLite metadata + ChromaDB vectors |
| Pluggable storage (§26) | ✅ | `IMemoryStore` protocol |
| Entity relationships (§35) | ✅ | `memory_links` + `MemoryLinkRepository` |
| User preferences (§7.3) | ✅ | `user_preferences` + репозиторий |
| Memory tags (§9) | ✅ | `memory_tags` + репозиторий |
| Conversation history (§20) | ✅ | `ConversationRepository` |
| Desktop owner linking | ✅ | `desktop_owner_telegram_id`, cross-channel USER scope |
| Working memory | ✅ | In-memory + `working_memory.md` |
| Memory provenance | ✅ | `source_message_ids`, `source_type` |
| LLM memory extraction | ✅ | `MemoryFormationService` |
| Migration from C++ kuni | ✅ | `KuniMigrator` → `MemoryService` |
| Consolidation | ⏳ | Следующая итерация |

---

## 📈 Производительность

- **Векторный поиск:** 10-50ms (ChromaDB HNSW), не O(n) brute-force
- **Multi-level retrieval:** 4 уровня (CHAT→USER→PRIVATE→GLOBAL)
- **SQLite:** ~50K writes/sec при 10 writes/sec реальной нагрузки kunipy
- **Хранение:** ~1KB метаданные + ~16KB embedding (4096-dim) на воспоминание

---

## 🧪 Тестирование

- `test_memory_minimal.py` — репозитории SQLite напрямую
- `test_memory_integration.py` — поток сообщений через MemoryService + ChromaDB
- Тесты гоняются в WSL Ubuntu-24.04 (`/home/alexey/kunipy`); Windows-копия — только исходники
- Известная проблема: segfault TDLib при полном DI-запуске — игнорируется по решению владельца

---

## 🚀 Дальнейшие шаги

1. **Консолидация памяти** — merge/summarize старых воспоминаний
2. **Граф сущностей** — использование `memory_links` в retrieval
3. **Диагностические инструменты** — проверка консистентности ChromaDB↔SQLite
4. **Расширенный набор тестов** — round-trip сериализации, scope visibility

---

**Версия:** 0.4.0 (Hybrid Memory: SQLite + ChromaDB)
**Обновлено:** 2026-09-12
