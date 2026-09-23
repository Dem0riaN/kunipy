# План реализации зрения для анимаций и естественной реакции персонажа

**Дата:** 2026-09-14  
**Обновлено:** 2026-09-19  
**Проект:** kunipy  
**Версия:** 0.6.0  
**Статус:** 📋 Планируется для будущих версий  
**Цель:** Персонаж должен видеть и естественно реагировать на стикеры/гифки/анимации, понимая их эмоциональный контекст

---

## 📸 Текущая реализация медиа (как есть)

### Поток обработки фото/стикеров

```
1. TelegramHandler.handle_new_message()
   ├─> _process_media() — обрабатывает voice/documents, 
   │                       НО photo/sticker пропускает с комментарием
   │                       "Photos and stickers: keep media metadata for multimodal content creation"
   │
   ├─> has_image_media = msg.media.get("type") in ("photo", "sticker")  ← только статика
   │
   └─> Передаёт notification с флагом has_image_media=True, telegram_message в metadata

2. Worker.handle_notification()
   ├─> Если has_image_media == True:
   │   ├─> MediaService.get_image_bytes_and_mime(telegram_msg)
   │   │   ├─> download_file_bytes(file_id) — скачивает raw bytes
   │   │   ├─> Для sticker: mime_type = "image/webp" (если статичный)
   │   │   ├─> Для animated/video sticker: return None (не поддерживается)
   │   │   └─> Для photo: mime_type = "image/jpeg"
   │   │
   │   └─> create_multimodal_content(text, image_bytes, mime_type)
   │       ├─> normalize_image_bytes() — WebP → PNG/JPEG "на лету"
   │       ├─> base64 encode
   │       └─> Формирует OpenAI multimodal content: [{"type":"text"}, {"type":"image_url"}]
   │
   └─> Отправляет multimodal content напрямую в LLM (основная модель с vision)
```

### Ключевые особенности

✅ **WebP нормализация работает:** `normalize_image_bytes()` конвертирует WebP → PNG/JPEG в памяти  
✅ **Прямая отправка в модель:** Нет промежуточного describe_photo — изображение идёт прямо в основную модель  
✅ **Промпты существуют но НЕ используются напрямую:**
   - `photo_to_text.md` — LEGACY путь через `describe_photo_message()` (отдельный vision endpoint)
   - `sticker_to_text.md` — НЕ используется (нет вызовов)
   - Основная модель получает изображение БЕЗ специального промпта для зрения

❌ **Анимации игнорируются:**
   - `media_service.py:134` — `return None` для `is_animated` или `is_video` стикеров
   - `telegram_handler.py:150` — `has_image_media` НЕ включает `"animation"`

❌ **Промпты зрения не применяются к основной модели:**
   - Модель видит только `text` из notification + изображение
   - Нет явной инструкции "опиши стикер эмоционально" или "детальная капшн"

---

## 🎭 Проблемы текущего подхода

### 1. Анимации: Первый кадр недостаточен

**Проблема:** Модель должна понимать происходящее на медиа. По первому кадру нельзя дать суждение о событиях через секунду/полторы/две.

**Пример:**
- Анимация: Капитан Шепард делает жест "рука-лицо" (facepalm)
- Первый кадр: Рука около головы
- Проблема: Непонятно, что это за жест (может быть салют, почёсывание, etc.)
- Нужно: Видеть начало → движение → итоговый жест

### 2. Промпты заставляют описывать, а не реагировать

**Текущее поведение (неправильное):**
```
User: [отправляет стикер с закатыванием глаз]
Модель видит: sticker_to_text.md промпт → "Опиши стикер: Title, Emotion, Meaning..."
Модель отвечает: "Title: Eye Roll, Emotion: Sarcasm, Intensity: Medium..."
```

**Нужное поведение:**
```
User: [отправляет стикер с закатыванием глаз]
Модель видит: Контекст разговора + изображение
Модель понимает: Сарказм/недоверие
Куни реагирует: "Ну ладно, ладно, не закатывай глаза 😏"
```

**Ключевое отличие:**
- ❌ НЕ НУЖНО: Structured описание стикера
- ✅ НУЖНО: Персонаж понимает эмоциональный посыл и реагирует естественно

---

## 💡 Решение

### Философия: "Персонаж видит стикер и реагирует естественно, как в живом диалоге"

**Аналогия:**
- Человек кидает стикер с facepalm → собеседник понимает "разочарование/сарказм" → отвечает соответственно
- Куни получает стикер → понимает эмоциональный посыл → отвечает в характере

---

## 🎬 Решение проблемы анимаций: N ключевых кадров

### Подход: Извлечь 3 кадра (начало, середина, конец) и показать последовательность

**Преимущества:**
- ✅ Модель видит динамику жеста/действия
- ✅ Понимает полную последовательность (начало → движение → итог)
- ✅ Совместимо с OpenAI API (multiple image_url в одном message)

**Недостатки:**
- ⚠️ 3x медленнее на inference (~1500ms вместо ~500ms на GPU)
- ⚠️ 3x больше vision токенов
- ✅ **Приемлемо:** Люди ждут 1-2 секунды на ответ в диалоге

### Реализация

#### Метод извлечения ключевых кадров

**Файл:** `src/application/media_service.py`

```python
async def _extract_keyframes(self, video_bytes: bytes, n_frames: int = 3) -> list[bytes]:
    """Extract N evenly-spaced keyframes from animation.
    
    For 2-second animation at 30fps (60 frames total):
    - n_frames=3 → extract frames 0, 30, 59 (start, middle, end)
    
    Args:
        video_bytes: Raw animation file bytes (gif/webm/mp4)
        n_frames: Number of keyframes to extract (default 3)
    
    Returns:
        List of JPEG frame bytes
    """
    try:
        from io import BytesIO
        from PIL import Image
        
        img = Image.open(BytesIO(video_bytes))
        
        # Get total frame count
        if not getattr(img, "is_animated", False):
            # Static image: return single frame
            output = BytesIO()
            img.convert("RGB").save(output, format="JPEG", quality=85)
            return [output.getvalue()]
        
        total_frames = getattr(img, "n_frames", 1)
        
        # Calculate frame indices (evenly spaced)
        if total_frames <= n_frames:
            indices = list(range(total_frames))
        else:
            step = (total_frames - 1) / (n_frames - 1)
            indices = [int(i * step) for i in range(n_frames)]
        
        frames = []
        for idx in indices:
            img.seek(idx)
            frame = img.convert("RGB")
            output = BytesIO()
            frame.save(output, format="JPEG", quality=85, optimize=True)
            frames.append(output.getvalue())
        
        logger.info(f"Extracted {len(frames)} keyframes from {total_frames} total frames")
        return frames
        
    except Exception as e:
        logger.error(f"Keyframe extraction failed: {e}")
        return []
```

#### Метод получения кадров анимации

**Файл:** `src/application/media_service.py`

```python
async def get_animation_frames(self, msg: TelegramMessage, n_frames: int = 3) -> list[tuple[bytes, str]] | None:
    """Download animation and extract keyframes.
    
    Args:
        msg: Message containing animation media
        n_frames: Number of keyframes to extract (default 3)
    
    Returns:
        List of (frame_bytes, "image/jpeg") tuples, or None if fails
    """
    if not msg.media:
        return None
    
    file_id = msg.media.get("file_id")
    if not file_id:
        return None
    
    try:
        raw_bytes = await self._telegram.download_file_bytes(file_id)
        if not raw_bytes:
            return None
        
        frames = await self._extract_keyframes(raw_bytes, n_frames)
        if not frames:
            return None
        
        return [(frame, "image/jpeg") for frame in frames]
        
    except Exception as e:
        logger.error(f"Animation frame extraction error: {e}")
        return None
```

#### Расширение get_image_bytes_and_mime для анимаций

**Файл:** `src/application/media_service.py`

Обновить существующий метод для поддержки animations:

```python
async def get_image_bytes_and_mime(self, msg: TelegramMessage) -> tuple[bytes, str] | None:
    """Download image/video bytes from photo/sticker/animation message.
    
    For animations (webm/mp4/gif): extracts first frame and returns as image.
    For static images (photo/webp stickers): returns as-is with normalization.
    
    Args:
        msg: Message containing photo, sticker, or animation media
        
    Returns:
        Tuple of (image_bytes, mime_type) or None if download/processing fails
        
    Note:
        For multiple frames from animations, use get_animation_frames() instead.
        This method returns only the first frame for backward compatibility.
    """
    if not msg.media:
        return None
    
    file_id = msg.media.get("file_id")
    if not file_id:
        logger.warning(f"Media message missing file_id: {msg.media.get('type')}")
        return None
    
    try:
        # Download file
        raw_bytes = await self._telegram.download_file_bytes(file_id)
        if not raw_bytes:
            logger.warning(f"Failed to download media file {file_id}")
            return None
        
        media_type = msg.media.get("type")
        
        # Handle animations: extract first frame (for backward compatibility)
        if media_type == "animation" or (
            media_type == "sticker" and (
                msg.media.get("is_animated") or msg.media.get("is_video")
            )
        ):
            frames = await self._extract_keyframes(raw_bytes, n_frames=1)
            if frames:
                return (frames[0], "image/jpeg")
            return None
        
        # Handle static stickers (WebP)
        elif media_type == "sticker":
            return (raw_bytes, "image/webp")
        
        # Handle photos
        elif media_type == "photo":
            return (raw_bytes, "image/jpeg")
        
        else:
            logger.warning(f"Unsupported media type for vision: {media_type}")
            return None
            
    except (ValueError, KeyError, TypeError, RuntimeError) as e:
        logger.error(f"Media download error: {e}")
        return None
```

#### Модификация create_multimodal_content для multiple images

**Файл:** `src/openai_chat.py`

```python
def create_multimodal_content(
    text: str, 
    images: list[tuple[bytes, str]]  # NEW: list of (bytes, mime) instead of single image
) -> list[dict]:
    """Create OpenAI-compatible multimodal content with text and multiple images.
    
    Args:
        text: Text content (can be empty)
        images: List of (image_bytes, mime_type) tuples
        
    Returns:
        List of content parts in OpenAI format:
        [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:..."}},
            {"type": "image_url", "image_url": {"url": "data:..."}},
            ...
        ]
    """
    import base64
    
    content_parts = []
    if text:
        content_parts.append({"type": "text", "text": text})
    
    for image_data, mime_type in images:
        # Normalize image format if needed
        if mime_type == "image/webp" or mime_type not in ("image/jpeg", "image/png"):
            image_data, mime_type = normalize_image_bytes(image_data, mime_type)
        
        b64 = base64.b64encode(image_data).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"
        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
    
    return content_parts
```

**Backward compatibility wrapper:**

```python
def create_multimodal_content_single(text: str, image_data: bytes, mime_type: str) -> list[dict]:
    """Backward compatibility wrapper for single image.
    
    DEPRECATED: Use create_multimodal_content() with images=[(bytes, mime)] instead.
    """
    return create_multimodal_content(text, [(image_data, mime_type)])
```

---

## 🎨 Решение проблемы промптов: Contextual понимание вместо описания

### Проблема: sticker_to_text.md заставляет описывать

Текущий промпт `sticker_to_text.md`:
```
Output format:
- Title: short recognizable name for the sticker.
- VisibleContent: factual description...
- Emotion: main emotion...
- Intensity: low / medium / high...
```

**Это не нужно!** Персонажу не нужен structured output с полями Title/Emotion/etc.

### Решение: Новый промпт vision_context.md

**Создать:** `prompts/vision_context.md`

```markdown
You are viewing an image (photo/sticker/animation) sent by the user in the conversation.

Your task is NOT to describe the image. Your task is to UNDERSTAND the emotional and communicative intent behind it, and react naturally in the conversation.

Guidelines:
- If it's a meme/reaction sticker: understand the emotion (sarcasm, frustration, joy, etc.)
- If it's a gesture or action: understand what it communicates (facepalm = disappointment, eye-roll = disbelief, thumbs up = approval)
- If it's a photo: understand the context (what the user is showing, why it's relevant)
- React as your character would in this situation — don't list "Title/Emotion/Meaning", just respond naturally

For animations/multiple frames: you're seeing the sequence of action (start → middle → end). Understand the full gesture or movement.

Examples:
- User sends facepalm sticker → You might reply with light teasing or acknowledgment of the situation
- User sends eye-roll animation → You understand sarcasm/disbelief and respond accordingly
- User sends photo of their code → You look at it and give relevant technical feedback

Stay in character. React naturally. Don't output structured descriptions.
```

### Применение в коде

**Файл:** `src/worker.py` (метод `handle_notification`, строка ~157)

```python
# Check if notification has image media
if notification.metadata and notification.metadata.get("has_image_media"):
    telegram_msg = notification.metadata.get("telegram_message")
    if telegram_msg and telegram_msg.media:
        media_type = telegram_msg.media.get("type")
        
        try:
            from .application.media_service import MediaService
            from .openai_chat import create_multimodal_content
            
            media_service = MediaService(
                telegram_client=self.telegram,
                openai_client=self.openai,
                config=self.config
            )
            
            # NEW: Extract frames for animations, single image for photos/static stickers
            if media_type == "animation" or (
                media_type == "sticker" and 
                (telegram_msg.media.get("is_animated") or telegram_msg.media.get("is_video"))
            ):
                # Multi-frame for animations
                frames = await media_service.get_animation_frames(telegram_msg, n_frames=3)
                if frames:
                    # Prepare text
                    enhanced_text = notification.message
                    if not notification.message.strip():
                        # If user sent sticker without text, add minimal context
                        enhanced_text = "(user sent an animated sticker)"
                    
                    user_message_content = create_multimodal_content(
                        text=enhanced_text,
                        images=frames  # 3 frames
                    )
                    logger.info(f"Created multimodal content with {len(frames)} frames")
            else:
                # Single image for photos/static stickers
                result = await media_service.get_image_bytes_and_mime(telegram_msg)
                if result:
                    image_bytes, mime_type = result
                    
                    enhanced_text = notification.message
                    if not notification.message.strip():
                        enhanced_text = "(user sent an image)"
                    
                    user_message_content = create_multimodal_content(
                        text=enhanced_text,
                        images=[(image_bytes, mime_type)]  # Single image as list
                    )
                    logger.info(f"Created multimodal content for {media_type}")
                    
        except Exception as e:
            logger.warning(f"Failed to create multimodal content: {e}")
            # Fall back to text-only
```

### Инжектирование vision_context в system prompt

**Файл:** `src/worker.py` или `src/memory_integrated_worker.py` (метод `_build_system_prompt`)

```python
async def _build_system_prompt(self, notification: Notification) -> str:
    """Build system prompt with memory, diary, and vision context."""
    
    # ... existing memory/diary logic ...
    
    base_prompt = build_system_prompt(
        config=self.config,
        working_memory_text=self._working_memory_context,
        diary_context=combined_diary,
    )
    
    # NEW: Add vision context instructions if vision is enabled
    if self.config.capability_vision:
        vision_context = self.prompt_loader.load("vision_context")
        base_prompt += f"\n\n{vision_context}"
    
    return base_prompt
```

**Принцип:**
- ✅ Vision инструкции всегда в system prompt (если vision включен)
- ✅ Не повторяются в каждом user message
- ✅ Персонаж понимает: "когда вижу изображение, реагирую естественно"

---

## 🔧 Дополнительные изменения

### Включить animations в has_image_media

**Файл:** `src/application/telegram_handler.py` (строка 150)

```python
# OLD:
has_image_media = msg.media and msg.media.get("type") in ("photo", "sticker")

# NEW:
has_image_media = msg.media and msg.media.get("type") in ("photo", "sticker", "animation")
```

### Добавить зависимость Pillow (если отсутствует)

**Файл:** `requirements.txt` или `pyproject.toml`

```toml
[project]
dependencies = [
    # ... existing ...
    "Pillow>=10.0.0",  # Для извлечения кадров из GIF/анимаций
]
```

**Примечание:** Pillow уже используется в `normalize_image_bytes()`, но нужно проверить наличие в зависимостях.

### Опциональная конфигурация

**Файл:** `config.example.toml`

Добавить комментарий:

```toml
[capabilities.vision]
enabled = true  # Включает зрение для фото/стикеров/гифок/анимаций
# Персонаж получает изображения напрямую в основную модель (qwen2.5-vl)
# Анимации (webm/mp4/gif): автоматически извлекается 3 ключевых кадра (начало/середина/конец)
# Статичные стикеры (webp): нормализуются в PNG/JPEG "на лету"

# animation_frames = 3  # Количество кадров для анимаций (1-5, default 3)
# animation_frames = 1  # Установить в 1 для ускорения (только первый кадр)
```

**Файл:** `src/config.py`

```python
@dataclass
class Config:
    # ... existing fields ...
    
    # Vision
    capability_vision: bool = False
    animation_frames: int = 3  # NEW: Number of frames to extract from animations
```

---

## 📊 Итоговый поток (финальная версия)

```
1. Пользователь отправляет анимированный стикер (facepalm webm)
   └─> TelegramHandler: has_image_media = True, type="sticker", is_video=True

2. Worker.handle_notification()
   ├─> MediaService.get_animation_frames(msg, n_frames=3)
   │   ├─> download_file_bytes(file_id) → webm bytes
   │   ├─> _extract_keyframes(bytes, n=3) → [frame0.jpg, frame1.jpg, frame2.jpg]
   │   └─> Возвращает 3 JPEG-кадра (начало, середина, конец жеста)
   │
   ├─> create_multimodal_content(
   │       text="(user sent an animated sticker)",  ← если без текста
   │       images=[(frame0, "image/jpeg"), (frame1, "image/jpeg"), (frame2, "image/jpeg")]
   │   )
   │   └─> Возвращает OpenAI-формат: [
   │           {"type": "text", "text": "(user sent an animated sticker)"},
   │           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},  # frame 0
   │           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},  # frame 1
   │           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}   # frame 2
   │       ]
   │
   └─> Отправка в LLM:
       System: "<character_base> + <vision_context: understand emotions, react naturally>"
       User: [text + 3 images showing facepalm sequence]

3. Qwen 2.5 VL
   ├─> Видит последовательность: рука поднимается → движется к лицу → facepalm
   ├─> Понимает: жест разочарования/сарказма
   └─> Реагирует как Куни:
       "Ох, что опять произошло? 😅" 
       (естественная реакция, БЕЗ "Title: Facepalm gesture, Emotion: Disappointment")
```

---

## ✅ Итоговый план реализации (чеклист)

| Этап | Действие | Файл | Описание |
|------|----------|------|----------|
| **1** | Создать `prompts/vision_context.md` | `prompts/vision_context.md` | Промпт "понимай и реагируй", не "описывай" |
| **2** | Добавить `_extract_keyframes(n=3)` | `src/application/media_service.py` | Извлечение 3 кадров из анимации |
| **3** | Добавить `get_animation_frames()` | `src/application/media_service.py` | Обёртка для анимаций |
| **4** | Обновить `get_image_bytes_and_mime()` | `src/application/media_service.py` | Поддержка animations (first frame fallback) |
| **5** | Модифицировать `create_multimodal_content()` | `src/openai_chat.py` | Поддержка `images: list[tuple]` вместо одного изображения |
| **6** | Добавить backward compatibility wrapper | `src/openai_chat.py` | `create_multimodal_content_single()` для старого кода |
| **7** | Обновить логику в `worker.py` | `src/worker.py` | Различать animation (3 кадра) vs static (1 кадр) |
| **8** | Инжектить `vision_context` в system | `src/worker.py` / `src/memory_integrated_worker.py` | Один раз в system prompt, не в каждое сообщение |
| **9** | Включить `"animation"` в `has_image_media` | `src/application/telegram_handler.py` | Расширить список типов |
| **10** | Добавить конфиг `animation_frames` | `src/config.py` | Опциональная настройка количества кадров |
| **11** | Обновить `config.example.toml` | `config.example.toml` | Документация новых возможностей |
| **12** | Проверить зависимости | `requirements.txt` / `pyproject.toml` | Убедиться что Pillow >= 10.0.0 |

---

## ⚡ Производительность

### Оценки для Qwen 2.5 VL 7B

- **Извлечение 3 кадров (Pillow):** ~100-200ms (в памяти, без записи на диск)
- **Vision inference (3 кадра):**
  - GPU (RTX 3060/4060): ~1500ms (500ms × 3)
  - CPU: ~4500ms (1500ms × 3)
- **Итого на GPU:** ~1.7 секунды (приемлемо для диалога)

### Оптимизация

Можно сделать config-флаг:
```toml
[capabilities.vision]
animation_frames = 3  # 1 = только первый кадр (быстрее), 3 = full sequence (точнее)
```

**Рекомендация:** 
- `animation_frames = 3` — по умолчанию (баланс скорость/качество)
- `animation_frames = 1` — для слабых GPU (только первый кадр)
- `animation_frames = 5` — для мощных систем (максимальная детализация)

---

## 🎯 Ожидаемый результат

### До изменений:
```
User: [отправляет webm стикер с facepalm]
Куни: (не видит стикер, потому что is_video=True → return None)
```

### После изменений:
```
User: [отправляет webm стикер с facepalm — 3 кадра: начало жеста → движение → итог]
Куни: (видит последовательность кадров, понимает эмоцию, реагирует естественно)
      "Ну что, опять сломалось? 😏"
```

---

## 🔄 Архитектурные принципы

✅ **Не удалён существующий функционал** — только добавления  
✅ **Нет God Objects** — каждый класс имеет одну ответственность:
   - `MediaService` — извлечение и нормализация медиа
   - `Worker` — оркестрация обработки сообщений
   - `create_multimodal_content()` — форматирование для LLM API

✅ **Clean Architecture:**
   - Domain: никаких изменений
   - Interfaces: расширение существующих методов
   - Application: MediaService получает новые методы
   - Infrastructure: без изменений

✅ **OOP:** Инкапсуляция логики извлечения кадров в MediaService

✅ **Backward Compatibility:** Старый код продолжит работать через wrapper

---

## 📝 Примечания

### Альтернативные подходы (не выбраны)

#### 1. Несколько кадров (N=5-10)
**Плюсы:** Максимальная детализация анимации  
**Минусы:** 5-10x медленнее, избыточно для большинства стикеров  
**Решение:** Сделать конфигурируемым через `animation_frames`

#### 2. Native video support
**Концепция:** Отправка raw video bytes в модель  
**Статус:** Qwen 2.5 VL не поддерживает видео напрямую (только изображения)  
**Будущее:** Можно добавить когда модели будут поддерживать

#### 3. Текстовое описание через промежуточную модель
**Концепция:** Извлечь кадры → описать каждый → суммаризировать LLM → отправить текст  
**Минусы:** Персонаж не видит сам визуал, два LLM вызова  
**Решение:** Не используем, прямая визуальная передача лучше

---

## 🚀 Следующие шаги после реализации

1. **Тестирование:**
   - Отправить webm/tgs стикер → проверить извлечение 3 кадров
   - Отправить gif анимацию → проверить корректность последовательности
   - Отправить статичный webp стикер → проверить что работает как раньше
   - Проверить естественность реакций персонажа

2. **Оптимизация:**
   - Измерить реальное время inference на целевом железе
   - Настроить `animation_frames` под производительность
   - Рассмотреть кэширование извлечённых кадров (опционально)

3. **Документация:**
   - Обновить README с примерами работы с анимациями
   - Добавить примеры в docs/

---

**Финальная версия:** Готов к реализации после утверждения пользователем  
**Дата создания плана:** 2026-09-14
