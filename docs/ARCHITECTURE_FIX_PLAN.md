# План архитектурных исправлений kunipy v0.5.0

**Дата создания:** 2026-09-14  
**Обновлено:** 2026-09-19  
**Статус:** ✅ Критичные исправления завершены в v0.5.0-v0.6.0  
**Проект:** kunipy  
**Версия:** 0.6.0

---

## 📊 Результаты архитектурного аудита

### Найдено нарушений:
- **God Objects:** 3 критичных, 2 warning
- **Временные имена:** 5 нарушений
- **Нарушения границ слоёв:** 8 нарушений

---

## 🔴 Критические проблемы (Приоритет 1)

### 1. God Objects

#### 1A. `src/tools.py` (814 строк) — **КРИТИЧНО**

**Проблема:** Монолитный файл со всеми инструментами + фреймворк управления

**Ответственности (слишком много):**
- Telegram messaging (send, search, get chats, open chats)
- Media generation (take_photo, record_audio via Stable Diffusion/TTS)
- Sticker management (send, list, save)
- Diary/memory queries (RAG search)
- Web search integration
- Group administration (ban users, remove messages, set roles)
- Message manipulation (edit, forward, delete, react)
- Chat membership (join, leave)
- Tool orchestration framework (ToolContext, Tool class, call routing)
- Anti-repeat checking and typing simulation

**Решение:** Разбить на модули по доменам (см. Задачу 2.1)

---

#### 1B. `src/diary.py` (553 строки) — **КРИТИЧНО**

**Проблема:** Legacy класс совмещает 10+ разных задач

**Ответственности:**
- File I/O (read/write .md diary files with JSON front matter)
- Vector store operations (ChromaDB queries and updates)
- Embedding generation (delegates to OpenAI)
- Similarity search (query with cosine similarity)
- Full-text search (search_by_text with substring matching)
- Entry management (add_entry, save, delete_entry, get_entry)
- Legacy migration (_migrate_legacy_entries from C++ format)
- Consolidation orchestration (delegates to consolidation service)
- Cache management (_load_cache, lazy loading)
- Usage stats tracking (score, usageCount, lastUsed updates)

**Решение:** Отметить как deprecated, не рефакторить (см. Задачу 2.2)

---

#### 1C. `src/infrastructure/memory/memory_service.py` (369 строк) — **КРИТИЧНО**

**Проблема:** Делает всё что связано с памятью

**Ответственности:**
- Conversation history storage (store_message to SQLite)
- Memory piece creation (create_memory to ChromaDB + SQLite dual-write)
- Embedding generation (embed_text wrapper)
- Multi-level context retrieval (CHAT/USER/PRIVATE/GLOBAL scopes)
- Working memory management (promises, plans, questions)
- User/chat repository coordination (ensures users/chats exist)
- Cross-channel user linking (desktop ↔ telegram)
- Scope resolution and access control (_resolve_accessible_scopes)
- Memory deduplication and ranking

**Решение:** Уже частично правильная архитектура — оставить (см. Задачу 2.3)

---

### 2. Временные имена (5 нарушений)

#### Нарушение 2A: `temporary_context` → `conversation_history`

**Локации:**
| Файл | Строка | Тип |
|------|--------|-----|
| `src/worker.py` | 82 | атрибут класса |
| `src/tools.py` | 38 | параметр |
| `src/tools.py` | 43 | атрибут класса |

**Текущий код (ПЛОХО):**
```python
# worker.py
class Worker:
    def __init__(self, ...):
        self.temporary_context: dict[int, list[Message]] = {}

# tools.py
class ToolContext:
    def __init__(self, args, logger, temporary_context, all_tool_calls=None):
        self.temporary_context = temporary_context
```

**Исправить на (ХОРОШО):**
```python
# worker.py
class Worker:
    def __init__(self, ...):
        self.conversation_history: dict[int, list[Message]] = {}

# tools.py
class ToolContext:
    def __init__(self, args, logger, conversation_history, all_tool_calls=None):
        self.conversation_history = conversation_history
```

**Обновить все места использования:**
```python
# Найти все:
grep -r "temporary_context" src/ --include="*.py"

# Заменить везде на:
conversation_history
```

**Тестирование:**
- Запустить проект
- Отправить сообщение в чат
- Проверить что история сохраняется и доступна в следующих сообщениях
- Проверить diary dump (не должен ломаться)

---

#### Нарушение 2B: `new_text` → `updated_text`

**Локации:**
| Файл | Строка | Тип |
|------|--------|-----|
| `src/telegram_client.py` | 409 | параметр |
| `src/tools.py` | 647 | параметр |

**Текущий код (ПЛОХО):**
```python
# telegram_client.py
async def edit_message(self, chat_id: int, message_id: int, new_text: str) -> None:
    ...

# tools.py
async def _message_edit(ctx: ToolContext) -> str:
    new_text = ctx.args["text"]
    await telegram.edit_message(chat_id, message_id, new_text)
```

**Исправить на (ХОРОШО):**
```python
# telegram_client.py
async def edit_message(self, chat_id: int, message_id: int, updated_text: str) -> None:
    ...

# tools.py
async def _message_edit(ctx: ToolContext) -> str:
    updated_text = ctx.args["text"]
    await telegram.edit_message(chat_id, message_id, updated_text)
```

**Тестирование:**
- Отправить сообщение
- Отредактировать через LLM tool
- Проверить что текст обновился

---

### 3. Нарушения границ слоёв (8 нарушений)

#### Нарушение 3A: MediaService вызывает LLM напрямую

**Файл:** `src/application/media_service.py`

**Проблема:** Extraction layer напрямую обращается к LLM layer

```python
# Line 90 (ПЛОХО):
text = await self._openai.transcribe_audio(audio_bytes, format="ogg")

# Line 259 (ПЛОХО):
description = await self._openai.describe_image(image_bytes, mime_type=mime_type)
```

**Решение:** Использовать интерфейс IOpenAIChat

**Проверить `src/interfaces/llm.py`:**
```python
class IOpenAIChat(Protocol):
    async def transcribe_audio(self, audio_bytes: bytes, format: str = "ogg") -> str:
        ...
    
    async def describe_image(
        self, 
        image_bytes: bytes, 
        mime_type: str,
        prompt: str | None = None
    ) -> str:
        ...
```

Если методов нет — добавить в интерфейс.

**Обновить MediaService:**
```python
# src/application/media_service.py
from ..interfaces.llm import IOpenAIChat  # Не OpenAIChat

class MediaService:
    def __init__(
        self,
        telegram_client: ITelegramClient,  # Интерфейс
        openai_client: IOpenAIChat,        # Интерфейс (УЖЕ правильный тип!)
        config: Config,
        extractor_registry: MediaExtractorRegistry | None = None
    ):
```

**Тестирование:**
- Отправить voice сообщение → проверить транскрипцию
- Отправить фото → проверить описание (если vision enabled)

---

#### Нарушение 3B: Worker импортирует TelegramClient напрямую

**Файл:** `src/worker.py:22`

**Проблема:** LLM layer импортирует конкретный Telegram класс вместо интерфейса

```python
# Line 22 (ПЛОХО):
from .telegram_client import TelegramClient

class Worker:
    def __init__(
        self,
        telegram: TelegramClient,  # Конкретный класс!
        ...
    ):
```

**Исправить на (ХОРОШО):**
```python
from .interfaces.telegram import ITelegramClient

class Worker:
    def __init__(
        self,
        telegram: ITelegramClient,  # Интерфейс!
        ...
    ):
```

**Обновить все методы в Worker** где используется `self.telegram` — они должны работать через интерфейс.

**Тестирование:**
- Запустить проект
- Проверить что все Telegram operations работают (send, edit, search)

---

#### Нарушение 3C: Worker создаёт MediaService inline

**Файл:** `src/worker.py:168`

**Проблема:** Runtime создание объекта внутри метода нарушает DI pattern

```python
# Line ~168 (ПЛОХО):
async def _generate_response(self, notification: Notification) -> str | None:
    # ...
    if notification.metadata and notification.metadata.get("has_image_media"):
        # Inline создание — BAD!
        media_service = MediaService(
            telegram_client=self.telegram,
            openai_client=self.openai,
            config=self.config
        )
        result = await media_service.get_image_bytes_and_mime(telegram_msg)
```

**Исправить на (ХОРОШО):**
```python
class Worker:
    def __init__(
        self,
        telegram: ITelegramClient,
        openai: IOpenAIChat,
        config: Config,
        media_service: MediaService | None = None,  # NEW: inject через DI
        ...
    ):
        self.telegram = telegram
        self.openai = openai
        self.config = config
        self.media_service = media_service  # Сохраняем
        ...
    
    async def _generate_response(self, notification: Notification) -> str | None:
        # ...
        if notification.metadata and notification.metadata.get("has_image_media"):
            # Использовать injected service
            if self.media_service:
                result = await self.media_service.get_image_bytes_and_mime(telegram_msg)
                if result:
                    image_bytes, mime_type = result
                    from .application.media.image_processor import create_multimodal_content
                    user_message_content = create_multimodal_content(
                        text=notification.message,
                        image_data=image_bytes,
                        mime_type=mime_type
                    )
```

**Обновить DI container:**
```python
# src/di/container.py
async def create_dependencies(...) -> Dependencies:
    # ...
    
    # Create MediaService ONCE
    media_service = MediaService(
        telegram_client=telegram_client,
        openai_client=openai_chat,
        config=config,
        extractor_registry=extractor_registry
    )
    
    # Inject into workers
    for i in range(config.worker_pool_size):
        worker = Worker(
            telegram=telegram_client,
            openai=openai_chat,
            config=config,
            media_service=media_service,  # NEW: передаём в Worker
            ...
        )
```

**Тестирование:**
- Отправить фото в чат
- Проверить что модель видит изображение (multimodal content created)
- Проверить логи: `Created multimodal content for photo`

---

#### Нарушение 3D: Image processing в openai_chat.py

**Файл:** `src/openai_chat.py:262, 311`

**Проблема:** Image processing функции находятся в LLM layer (должны быть в extraction/media layer)

```python
# Line 262 (ПЛОХО — не тот слой):
def normalize_image_bytes(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Normalize image bytes to PNG or JPEG format."""
    from PIL import Image
    # ... image processing logic ...

# Line 311 (ПЛОХО — не тот слой):
def create_multimodal_content(text: str, image_data: bytes, mime_type: str) -> list[dict]:
    """Create OpenAI-compatible multimodal content."""
    # ... content builder logic ...
```

**Исправить:** Создать `src/application/media/image_processor.py`

```python
"""Image processing utilities for multimodal content.

This module handles image normalization and multimodal content creation.
Separation from LLM layer follows Clean Architecture principles:
- Image processing is extraction/media layer responsibility
- LLM layer should only handle HTTP/API communication
"""

from io import BytesIO
import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_image_bytes(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Normalize image bytes to PNG or JPEG format.
    
    Handles WebP decoding and ensures the image is in a format compatible
    with vision models. Conversion happens entirely in memory.
    
    Args:
        image_data: Raw image bytes (any format Pillow supports)
        mime_type: Original MIME type (e.g., "image/webp", "image/jpeg")
    
    Returns:
        Tuple of (normalized_bytes, normalized_mime_type)
        - For images with transparency: PNG
        - For images without transparency: JPEG (smaller size)
    
    Raises:
        RuntimeError: If image cannot be decoded
    """
    try:
        from PIL import Image
        
        # Decode image
        img = Image.open(BytesIO(image_data))
        
        # Determine output format based on transparency
        has_alpha = img.mode in ("RGBA", "LA", "P") and (
            img.mode == "P" and "transparency" in img.info or img.mode in ("RGBA", "LA")
        )
        
        output = BytesIO()
        if has_alpha:
            # Preserve transparency with PNG
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png"
        else:
            # Convert to JPEG for better compression
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue(), "image/jpeg"
    except Exception as e:
        logger.error(f"Failed to normalize image: {e}")
        raise RuntimeError(f"Image normalization failed: {e}") from e


def create_multimodal_content(text: str, image_data: bytes, mime_type: str) -> list[dict[str, Any]]:
    """Create OpenAI-compatible multimodal content with text and image.
    
    Args:
        text: Text content (can be empty)
        image_data: Image bytes
        mime_type: Image MIME type
    
    Returns:
        List of content parts in OpenAI format:
        [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:..."}}
        ]
    """
    # Normalize image format if needed
    if mime_type == "image/webp" or mime_type not in ("image/jpeg", "image/png"):
        image_data, mime_type = normalize_image_bytes(image_data, mime_type)
    
    b64 = base64.b64encode(image_data).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    
    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
    
    return content_parts
```

**Оставить backward compatibility wrappers в openai_chat.py:**
```python
# src/openai_chat.py
# ... rest of the file ...

# Backward compatibility (DEPRECATED)
def normalize_image_bytes(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
    """DEPRECATED: Use application.media.image_processor.normalize_image_bytes instead."""
    import warnings
    warnings.warn(
        "normalize_image_bytes moved to application.media.image_processor",
        DeprecationWarning,
        stacklevel=2
    )
    from .application.media.image_processor import normalize_image_bytes as _new
    return _new(image_data, mime_type)

def create_multimodal_content(text: str, image_data: bytes, mime_type: str) -> list[dict]:
    """DEPRECATED: Use application.media.image_processor.create_multimodal_content instead."""
    import warnings
    warnings.warn(
        "create_multimodal_content moved to application.media.image_processor",
        DeprecationWarning,
        stacklevel=2
    )
    from .application.media.image_processor import create_multimodal_content as _new
    return _new(text, image_data, mime_type)
```

**Обновить импорты:**
```python
# src/worker.py
# OLD:
from .openai_chat import create_multimodal_content

# NEW:
from .application.media.image_processor import create_multimodal_content

# src/application/media_service.py
# OLD: (если используется)
from ..openai_chat import normalize_image_bytes

# NEW:
from .image_processor import normalize_image_bytes
```

**Тестирование:**
- Отправить webp стикер → проверить что конвертируется в PNG/JPEG
- Проверить что multimodal content создаётся корректно

---

#### Нарушение 3E: Tools импортирует TelegramClient напрямую

**Файл:** `src/tools.py:26`

**Проблема:** Аналогично Worker — прямое использование конкретного класса

```python
# Line 26 (ПЛОХО):
from .telegram_client import TelegramClient

# Line in create_default_tools:
def create_default_tools(
    telegram: TelegramClient,  # Конкретный класс!
    ...
):
```

**Исправить на (ХОРОШО):**
```python
from .interfaces.telegram import ITelegramClient

def create_default_tools(
    telegram: ITelegramClient,  # Интерфейс!
    ...
):
```

**Обновить все функции create_*_tools()** в файле — они должны принимать ITelegramClient.

**Тестирование:**
- Проверить что все инструменты работают (sticker_send, photo, search)

---

## 🟡 Структурные улучшения (Приоритет 2)

### Задача 2.1: Разбить tools.py на модули

**Проблема:** 814 строк в одном файле, 10+ ответственностей

**Решение:** Создать `src/tools/` директорию с модулями по доменам

**Структура:**
```
src/tools/
  __init__.py           # Экспорт create_default_tools(), Tool, ToolContext
  base.py               # Tool, ToolContext, OpenAITools (framework)
  telegram.py           # Telegram messaging tools (send_message, get_chats, open_chat)
  media.py              # Photo, audio generation (take_photo, record_audio)
  sticker.py            # Sticker tools (send, list, save)
  diary.py              # Diary RAG tools (diary_ask, diary_search)
  web.py                # Web search (web_search)
  admin.py              # Group admin tools (ban_user, remove_message, set_role)
  message.py            # Message edit/delete/forward/react
  chat.py               # Chat join/leave/open
```

**Пример `src/tools/sticker.py`:**
```python
"""Sticker management tools."""

from .base import Tool, ToolContext
from ..interfaces.telegram import ITelegramClient

def create_sticker_tools(
    telegram: ITelegramClient,
    chat: TelegramChat | None = None,
) -> list[Tool]:
    """Create sticker-related tools."""
    tools = []
    
    async def _sticker_send(ctx: ToolContext) -> str:
        chat_id = ctx.args.get("chat_id") or (chat.id if chat else 0)
        if not chat_id:
            return "Error: no chat_id available to send the sticker to."
        await telegram.send_sticker(chat_id, ctx.args["sticker"])
        return f"Sticker {ctx.args['sticker']} sent."
    
    tools.append(Tool(
        name="sticker_send",
        description="Send a sticker (by its Telegram file_id) to the current chat.",
        parameters={
            "type": "object",
            "properties": {
                "sticker": {"type": "string", "description": "Sticker file_id (see sticker_list)"},
                "chat_id": {"type": "integer", "description": "Optional: target chat ID. Defaults to current chat."},
            },
            "required": ["sticker"],
        },
        handler=_sticker_send,
    ))
    
    # ... rest of sticker tools ...
    
    return tools
```

**`src/tools/__init__.py`:**
```python
"""Tools package for LLM function calling.

This package provides organized tool modules by domain:
- base: Framework classes (Tool, ToolContext, OpenAITools)
- telegram: Messaging tools
- media: Photo/audio generation
- sticker: Sticker management
- diary: Diary RAG queries
- web: Web search
- admin: Group administration
- message: Message manipulation
- chat: Chat membership
"""

from .base import Tool, ToolContext, OpenAITools
from .telegram import create_telegram_tools
from .media import create_media_tools
from .sticker import create_sticker_tools
from .diary import create_diary_tools
from .web import create_web_tools
from .admin import create_admin_tools
from .message import create_message_tools
from .chat import create_chat_tools


def create_default_tools(
    telegram: ITelegramClient,
    openai: IOpenAIChat,
    diary: Diary | None,
    config: Config,
    chat: TelegramChat | None = None,
) -> OpenAITools:
    """Create and register all default tools.
    
    Returns:
        OpenAITools container with all tools registered
    """
    tools = OpenAITools()
    
    # Register tools from each module
    for tool in create_telegram_tools(telegram, chat):
        tools.insert(tool)
    
    for tool in create_media_tools(telegram, chat):
        tools.insert(tool)
    
    for tool in create_sticker_tools(telegram, chat):
        tools.insert(tool)
    
    if diary:
        for tool in create_diary_tools(diary):
            tools.insert(tool)
    
    for tool in create_web_tools(config):
        tools.insert(tool)
    
    for tool in create_admin_tools(telegram, chat):
        tools.insert(tool)
    
    for tool in create_message_tools(telegram, chat):
        tools.insert(tool)
    
    for tool in create_chat_tools(telegram, chat):
        tools.insert(tool)
    
    return tools
```

**Обновить импорты в Worker:**
```python
# src/worker.py
# OLD:
from .tools import OpenAITools, create_default_tools

# NEW:
from .tools import OpenAITools, create_default_tools  # Путь не меняется!
```

**ВАЖНО:**
- Функционал не должен измениться
- Только структура файлов меняется
- Обратная совместимость через `__init__.py`

**Тестирование:**
- Запустить проект
- Проверить что все инструменты работают (send message, sticker, photo, diary search)
- Проверить logs: не должно быть import errors

**Оценка времени:** 2 часа

---

### Задача 2.2: Отметить diary.py как deprecated

**Проблема:** 553 строк, God Object, но legacy код

**Решение:** НЕ рефакторить, только добавить deprecation комментарии

**Обоснование:**
- Уже существует новая архитектура памяти (MemoryService + ChromaDB)
- diary.py — legacy C++ формат, используется только для:
  1. Чтения старых записей
  2. Миграции в новый формат (через KuniMigrator)
  3. Auto-RAG injection для исторического контекста
- Рефакторинг legacy кода не приоритет
- Новый функционал идёт через MemoryService

**Добавить в начало файла:**
```python
"""Legacy diary implementation (C++ kuni format).

DEPRECATED: This module maintains backward compatibility with C++ kuni diary format.
New code should use infrastructure.memory.MemoryService instead.

This class will remain for:
1. Reading legacy diary entries (C++ kuni JSON+markdown format)
2. Migration to new format (via KuniMigrator)
3. Auto-RAG injection for historical context in prompts

Do NOT extend this class with new features.
Do NOT refactor — it works as-is for its legacy purpose.

For new diary/memory functionality:
- Use MemoryService (src/infrastructure/memory/memory_service.py)
- Use WorkingMemory (src/infrastructure/memory/working_memory.py)
- Use DiaryContextInjector (src/infrastructure/memory/diary_context_injector.py)
"""

from __future__ import annotations
# ... rest of imports ...
```

**Добавить deprecation warning в __init__:**
```python
class Diary:
    """Legacy diary implementation (C++ kuni format).
    
    DEPRECATED: Use MemoryService for new code.
    This class exists only for backward compatibility with existing diary files.
    """
    
    def __init__(self, ...):
        import warnings
        warnings.warn(
            "Diary is deprecated. Use MemoryService for new functionality.",
            DeprecationWarning,
            stacklevel=2
        )
        # ... rest of init ...
```

**Оценка времени:** 5 минут

---

## 📋 Итоговый чеклист

### Фаза 1: Критичные исправления (обязательно, ~90 минут)

| № | Задача | Файлы | Время |
|---|--------|-------|-------|
| **1.1** | Переименовать `temporary_context` → `conversation_history` | worker.py, tools.py | 15 мин |
| **1.2** | Переименовать `new_text` → `updated_text` | telegram_client.py, tools.py | 5 мин |
| **1.3** | Заменить прямой импорт TelegramClient на ITelegramClient | worker.py, tools.py | 10 мин |
| **1.4** | Переместить image_processor из openai_chat в application/media | NEW: image_processor.py, UPDATE: openai_chat.py, worker.py | 30 мин |
| **1.5** | Проверить IOpenAIChat интерфейс (transcribe_audio, describe_image) | interfaces/llm.py | 10 мин |
| **1.6** | Инжектить MediaService в Worker через DI | worker.py, di/container.py | 20 мин |

**Итого Фазы 1:** 90 минут

---

### Фаза 2: Структурные улучшения (опционально, ~2 часа)

| № | Задача | Файлы | Время |
|---|--------|-------|-------|
| **2.1** | Разбить tools.py на модули (src/tools/ directory) | NEW: tools/*.py, UPDATE: imports | 2 часа |
| **2.2** | Отметить diary.py как deprecated (комментарии) | diary.py | 5 мин |

**Итого Фазы 2:** 2 часа 5 минут

---

## 🎯 Порядок выполнения

### Фаза 1: Критичные исправления (обязательно)

1. **Переименования (1.1, 1.2)**
   - Не ломают архитектуру
   - Безопасно (простой find/replace)
   - Убирает временные имена

2. **Интерфейсы (1.3, 1.5)**
   - Исправляют нарушения DI
   - Требуют проверки ITelegramClient, IOpenAIChat

3. **Image processor (1.4)**
   - Исправляет layer violations
   - Создаёт новую структуру application/media/

4. **DI injection (1.6)**
   - Завершает правильную архитектуру
   - Требует обновления DI container

### Фаза 2: Структурные улучшения (опционально)

5. **Разбить tools.py (2.1)**
   - Улучшает читаемость
   - Не ломает функционал
   - Большая работа (2 часа)

6. **Пометить diary.py (2.2)**
   - Документация
   - Предупреждение о legacy

---

## ✅ Критерии завершения

### После Фазы 1:
- [ ] Все временные имена переименованы
- [ ] Worker, Tools используют интерфейсы (ITelegramClient, IOpenAIChat)
- [ ] Image processing в application/media/
- [ ] MediaService инжектится через DI
- [ ] Проект запускается без ошибок
- [ ] Все инструменты работают (sticker_send, photo, search)
- [ ] Multimodal content (фото/стикеры) работает

### После Фазы 2 (опционально):
- [ ] tools.py разбит на модули
- [ ] diary.py помечен как deprecated
- [ ] Проект запускается без ошибок
- [ ] Все инструменты работают

---

## 🧪 Тестирование после каждой задачи

### После переименований (1.1, 1.2):
```bash
cd /home/alexey/dev/kunipy
source .venv/bin/activate
python run.py
# Отправить сообщение, отредактировать, проверить логи
```

### После интерфейсов (1.3, 1.5):
```bash
python run.py
# Проверить что все Telegram operations работают
```

### После image processor (1.4):
```bash
python run.py
# Отправить webp стикер → проверить конвертацию в PNG/JPEG
# Отправить фото → проверить что multimodal content создаётся
```

### После DI injection (1.6):
```bash
python run.py
# Отправить фото в чат
# Проверить логи: "Created multimodal content for photo"
```

### После разбивки tools.py (2.1):
```bash
python run.py
# Проверить что все инструменты работают:
# - sticker_send
# - take_photo
# - diary_search
# - web_search
# - edit_message
```

---

## 📝 Примечания

### Что НЕ делать:
- ❌ Не рефакторить diary.py (legacy, работает)
- ❌ Не трогать TelegramClient (Facade pattern, приемлемо)
- ❌ Не трогать TelegramEventHandler (Orchestrator, приемлемо)
- ❌ Не удалять функционал — только добавлять/улучшать

### Что делать:
- ✅ Переименовать временные имена
- ✅ Исправить нарушения DI
- ✅ Разделить слои (extraction, LLM, Telegram)
- ✅ Разбить монолитные файлы по доменам
- ✅ Добавить deprecation warnings для legacy кода

---

**Дата создания:** 2026-09-14  
**Статус:** Готов к выполнению  
**Следующий шаг:** Начать Фазу 1 (критичные исправления)
