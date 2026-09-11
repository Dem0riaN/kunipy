# Анализ существующей системы памяти (ТЗ-002 Этап 1)

## Дата: 2026-09-11

## 1. Существующая реализация в kunipy

### 1.1 Diary (src/diary.py)

**Текущее состояние:**
- Основная система памяти базируется на `DiaryEntry`
- Хранение: файлы `.md` в `diary_dir`
- Формат: JSON metadata + markdown body
- Embedding: через OpenAI API (text-embedding-3-small по умолчанию)
- Retrieval: cosine similarity с confidence factor
- Consolidation: заглушка (placeholder)

**Структура DiaryEntry:**
```python
id: str
text: str
metadata: dict[str, Any]
  - embedding: list[float]
  - confidence: float (0.0)
  - last_used: ISO timestamp
  - usage_count: int (0)
body: str
```

**Ключевые методы:**
- `query()` - embedding-based kNN retrieval
- `add_entry()` - добавление с проверкой дубликатов (plagiarism_threshold)
- `sleep_consolidation()` - заглушка
- `_get_embedding()` - через OpenAI
- `_cosine_similarity()` - numpy-based

**Параметры конфигурации:**
- `diary_min_relatedness` - минимальный порог similarity
- `diary_plagiarism_threshold` - порог дубликатов
- `embedding.model` - модель embeddings

**Ограничения текущей реализации:**
- ❌ Нет разделения пользователей/чатов
- ❌ Вся память в одной плоской структуре
- ❌ Нет visibility/scope
- ❌ Нет provenance
- ❌ Нет working memory
- ❌ Нет многоканальности
- ❌ Consolidation не реализован
- ❌ Confidence не управляется динамически
- ✅ Есть embedding-based retrieval
- ✅ Есть базовая модель confidence
- ✅ Есть файловое хранение с metadata

### 1.2 Интерфейсы (src/interfaces/memory.py)

**Уже определены (заготовка под ТЗ-002):**

**MemoryScope enum:**
- PRIVATE, USER, CHAT, SHARED, GLOBAL

**MemoryKind enum:**
- ENTITY_DESCRIPTION, THOUGHT, EVENT, FACT, OTHER

**MemoryPiece dataclass:**
```python
id, kind, content, confidence, importance
created_at, updated_at, last_used, usage_count
embedding: list[float]
scope: MemoryScope
user_id, chat_id, channel
source_message_ids, source_type
retrieval_cues, entities, metadata
```

**WorkingMemoryContext dataclass:**
```python
user_id, chat_id, channel
current_topic, conversation_summary
pending_questions, promises, plans
last_interaction, emotion_state
metadata
```

**Протоколы (stub):**
- `IMemoryStore` - CRUD + search operations
- `IWorkingMemory` - context management

### 1.3 Embedding cache (src/infrastructure/memory/embedding_cache.py)

**Реализован:**
- In-memory кэш embeddings с TTL (default 1 hour)
- Методы: get, set, clear, evict_expired, get_stats
- Метрики: hits, misses, hit_rate

## 2. Анализ оригинального kuni (C++)

**Источник:** alex2772/kuni

**Необходимо изучить:**
- [ ] Формат хранения memory pieces (файлы/БД?)
- [ ] Модель embeddings (какая размерность?)
- [ ] Реализация retrieval (kNN? ANN?)
- [ ] Формат diary
- [ ] Sleep-time consolidation логика
- [ ] Memory prompt формирование
- [ ] Confidence calculation/update
- [ ] Memory merge/split/delete логика
- [ ] Архив памяти (формат файлов)

**Примечание:** Для полного анализа требуется доступ к репозиторию alex2772/kuni

## 3. Существующий архив памяти

**Расположение:** (уточнить в конфигурации)
- Вероятно: `~/.kuni/diary/` или аналогичный путь
- Формат: `.md` файлы с JSON metadata

**Требования:**
- ✅ Архив должен остаться читаемым
- ✅ Миграция без изменения исходных файлов
- ✅ Возможность повторной миграции

## 4. Gaps в текущей реализации

### Критические (блокируют ТЗ-002):
1. **Нет разделения контекстов**
   - Все сообщения всех пользователей в одной памяти
   - Невозможно различить User A и User B

2. **Нет scope/visibility**
   - Интерфейс определён, но не используется
   - Нет фильтрации при retrieval

3. **Нет working memory runtime**
   - Интерфейс определён, но нет реализации
   - Нет хранения promises/plans/pending_questions

4. **Нет multi-channel support**
   - Telegram/desktop/voice не различаются
   - Нет связи desktop-владелец ↔ Telegram ID

5. **Нет conversation history storage**
   - Сообщения не сохраняются как отдельная история
   - Memory pieces не имеют provenance к исходным сообщениям

6. **Consolidation не реализован**
   - Только placeholder
   - Нет merge/split/delete логики

### Некритические (можно отложить):
- Relationships между entities
- Retrieval cues автоматическое извлечение
- Importance динамическое вычисление
- Emotion state tracking

## 5. Требования к новой архитектуре

### 5.1 Storage Layer
```
Memory Storage
├── Conversation Store (история сообщений)
│   └── По user_id + chat_id + channel
├── Memory Store (долговременная память)
│   └── По scope + user_id/chat_id
├── Vector Store (embeddings для retrieval)
│   └── ANN/kNN index
└── Working Memory Store (текущее состояние)
    └── По user_id + chat_id
```

### 5.2 Retrieval Pipeline
```
Query → Context Resolution → Multi-level Retrieval → Visibility Filter → Ranking → Context Assembly
```

### 5.3 Memory Lifecycle
```
Message → Conversation → Memory Formation → Long-term Storage → Consolidation
          ↓
      Working Memory → Plans/Promises → Transfer or Expire
```

## 6. Архитектурные решения

### 6.1 Хранилище
**Варианты:**
1. **Файловое + SQLite** (минимальные зависимости)
   - Conversations: SQLite
   - Memory pieces: SQLite + файлы embeddings
   - Working memory: JSON files или SQLite
   
2. **PostgreSQL + pgvector** (production-ready)
   - Всё в одной БД
   - Нативная поддержка vector similarity
   - ACID гарантии
   
3. **Гибрид** (рекомендуется для Phase 1)
   - Conversations + Memory metadata: SQLite
   - Embeddings: отдельные numpy файлы или встроенные в SQLite
   - Working memory: JSON files (быстрый доступ)
   - Миграция на PostgreSQL в Phase 2

**Решение для Phase 1:** SQLite + filesystem

### 6.2 Embedding Store
- Dimension: 1536 (text-embedding-3-small) или 3072 (text-embedding-3-large)
- Storage: SQLite BLOB или numpy .npy files
- Index: in-memory kNN (для начала) → FAISS/Annoy в Phase 2

### 6.3 Context Resolution
```python
@dataclass
class RetrievalContext:
    user_id: str
    chat_id: str
    channel: str
    query_text: str
    query_embedding: list[float]
    
    # Resolved scopes
    accessible_scopes: list[MemoryScope]
    is_desktop_owner: bool
    linked_user_ids: list[str]  # For cross-channel
```

## 7. План реализации (детализация)

### Phase 1: Foundation (текущий этап)
- [x] Анализ существующей системы
- [ ] Проектирование моделей данных
- [ ] Реализация Conversation Store (SQLite)
- [ ] Реализация Memory Store (SQLite + embeddings)
- [ ] Реализация Working Memory (JSON/SQLite)
- [ ] Базовый Retrieval с scope filtering
- [ ] Context Resolution
- [ ] Stub Consolidation

### Phase 2: Integration
- [ ] Подключение к Telegram handler
- [ ] Подключение к Desktop handler (когда будет)
- [ ] Memory formation после сообщений
- [ ] Working memory lifecycle
- [ ] Миграция существующего diary

### Phase 3: Advanced Features
- [ ] Sleep-time consolidation (real)
- [ ] Confidence management
- [ ] Importance calculation
- [ ] Relationships
- [ ] Diagnostics tools

## 8. Риски и митигация

**Риск 1:** Формат оригинального kuni архива неизвестен
- **Митигация:** Начать с kunipy diary.py формата, он уже читаемый

**Риск 2:** Производительность retrieval при большом объёме памяти
- **Митигация:** Phase 1 - простой kNN, Phase 2 - FAISS/Annoy

**Риск 3:** Сложность consolidation логики
- **Митигация:** Phase 1 - stub, Phase 2 - базовая логика, Phase 3 - LLM-based

**Риск 4:** Desktop-владелец linking требует конфигурацию
- **Митигация:** Добавить в config.toml опциональное поле `desktop_owner_telegram_id`

## 9. Следующие шаги

1. ✅ Завершить анализ
2. → Спроектировать database schema
3. → Реализовать Conversation Store
4. → Реализовать Memory Store
5. → Реализовать базовый Retrieval
6. → Написать тесты
7. → Интегрировать в telegram_handler

---

**Статус:** Этап 1 (Исследование) завершён
**Следующий:** Этап 2 (Проектирование)
