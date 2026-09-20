# План внедрения исправлений для kunipy

**Обновлено:** 2026-09-19  
**Статус:** ✅ Критичные баги исправлены, автономность восстановлена (v0.6.0)

## Приоритеты

### ✅ ФАЗА 0: КРИТИЧНЫЕ БАГИ (ЗАВЕРШЕНО)
**Статус:** ✅ Выполнено в v0.5.0-v0.6.0  
**Время:** Завершено  
**Риск:** Устранён

#### Задача 0.1: Исправить чтение papik_name
**Файл:** `src/config.py`  
**Строка:** 242-246  
**Действие:** Добавить чтение `papik_name` из секции `[character]`

```python
# БЫЛО:
character = data.get("character", {})
cfg.character_name = character.get("name", cfg.character_name)
# Owner (papik) - read from [character] section
cfg.papik_chat_id = character.get("papik_chat_id", cfg.papik_chat_id)

# СТАЛО:
character = data.get("character", {})
cfg.character_name = character.get("name", cfg.character_name)
cfg.papik_name = character.get("papik_name", cfg.papik_name)  # ← ДОБАВИТЬ
# Owner (papik) - read from [character] section
cfg.papik_chat_id = character.get("papik_chat_id", cfg.papik_chat_id)
```

**Проверка:**
```bash
python -c "from src.config import load_config; cfg = load_config('config.toml'); print(f'papik_name: {cfg.papik_name}')"
```
Ожидаемый результат: `papik_name: Artellin` (не пустая строка)

---

#### Задача 0.2: Добавить can_write_to_a_new_person
**Файлы:** 
- `src/config.py` (Config класс)
- `src/config.py` (парсер)
- `config.example.toml`

**Действие 1:** Добавить в Config класс (после строки 95):
```python
# Lockdown
lockdown: LockdownMode = LockdownMode.NONE
can_write_to_a_new_person: bool = False  # ← ДОБАВИТЬ ЭТУ СТРОКУ
```

**Действие 2:** Добавить в парсер (после строки 285):
```python
# Lockdown
lockdown_cfg = data.get("lockdown", {})
mode_str = lockdown_cfg.get("mode", "none")
cfg.lockdown = LockdownMode(mode_str) if mode_str else LockdownMode.NONE
cfg.can_write_to_a_new_person = lockdown_cfg.get("can_write_to_a_new_person", cfg.can_write_to_a_new_person)  # ← ДОБАВИТЬ
```

**Действие 3:** Добавить в `config.example.toml` (в секцию [lockdown], после mode):
```toml
[lockdown]
# Режим блокировки / Lockdown mode
# "none" - все могут писать / anyone can write
# "contacts_only" - только контакты / contacts only
# "papik_only" - только владелец / owner only
mode = "papik_only"

# Позволить боту самостоятельно писать новым людям без истории общения
# Allow bot to proactively write to new people without prior conversation history
# false = предотвращает использование как спам-бот / prevents using as spam bot
can_write_to_a_new_person = false
```

**Проверка:**
```bash
python -c "from src.config import load_config; cfg = load_config('config.toml'); print(f'can_write_to_a_new_person: {cfg.can_write_to_a_new_person}')"
```
Ожидаемый результат: `can_write_to_a_new_person: False` (без AttributeError)

---

#### Задача 0.3: Обновить config.toml (рабочий конфиг)
**Файл:** `config.toml`  
**Действие:** Добавить `can_write_to_a_new_person = false` в секцию `[lockdown]`

```toml
[lockdown]
mode = "contacts_only"

# Добавить эту строку:
can_write_to_a_new_person = false
```

---

### ⚠️ ФАЗА 1: ВЫСОКОПРИОРИТЕТНЫЕ ПАРАМЕТРЫ (в течение недели)
**Статус:** Рекомендуется  
**Время:** ~2-3 часа  
**Риск:** СРЕДНИЙ - функционал неполный

#### Задача 1.1: Добавить недостающие misc параметры
**Файл:** `config.example.toml`  
**Действие:** Добавить новую секцию `[misc]` с параметрами из C++ kuni

```toml
# ============================================================
# ДОПОЛНИТЕЛЬНЫЕ ПАРАМЕТРЫ / MISC PARAMETERS
# ============================================================

[misc]
# Максимальная длина истории чата (в символах)
# Maximum chat history length (in characters)
chat_max_history_length = 2000

# Вероятность напомнить о доступных инструментах (0.0 - 1.0)
# Probability to remind about available tools (0.0 - 1.0)
tool_reminder_probability = 0.02

# Параметры обработки видео / Video processing parameters
# Максимум кадров для извлечения из видео
# Maximum frames to extract from video
video_max_frames = 16

# Минимальный интервал между кадрами (мс)
# Minimum interval between frames (ms)
video_min_step_ms = 1000

# Просыпаться при сообщениях в закреплённых чатах (не только от владельца)
# Wake up on messages in pinned chats (not only from owner)
wake_up_on_pinned_chat = false
```

#### Задача 1.2: Добавить параметры в Config класс
**Файл:** `src/config.py`  
**Действие:** Добавить поля в Config dataclass (после строки 178)

```python
# Notification filtering
chat_notification_filter: LockdownMode = LockdownMode.NONE
suggest_ignore_chance: float = 0.0

# Misc parameters (from C++ kuni)
chat_max_history_length: int = 2000
tool_reminder_probability: float = 0.02
video_max_frames: int = 16
video_min_step_ms: int = 1000
wake_up_on_pinned_chat: bool = False
```

#### Задача 1.3: Добавить парсинг misc параметров
**Файл:** `src/config.py`  
**Действие:** Добавить чтение misc секции (после парсинга worker, перед return cfg)

```python
# Misc parameters (C++ kuni compatibility)
misc_cfg = data.get("misc", {})
cfg.chat_max_history_length = misc_cfg.get("chat_max_history_length", cfg.chat_max_history_length)
cfg.tool_reminder_probability = misc_cfg.get("tool_reminder_probability", cfg.tool_reminder_probability)
cfg.video_max_frames = misc_cfg.get("video_max_frames", cfg.video_max_frames)
cfg.video_min_step_ms = misc_cfg.get("video_min_step_ms", cfg.video_min_step_ms)
cfg.wake_up_on_pinned_chat = misc_cfg.get("wake_up_on_pinned_chat", cfg.wake_up_on_pinned_chat)
```

---

### 📋 ФАЗА 2: TELEGRAM MTPROTO ПРОКСИ (опционально)
**Статус:** Низкий приоритет  
**Время:** ~1 час  
**Риск:** НИЗКИЙ - редко используемая функция

#### Задача 2.1: Добавить MTProto прокси в config
**Файл:** `config.example.toml`  
**Действие:** Добавить в секцию `[telegram]`

```toml
[telegram]
# ... существующие параметры ...

# MTProto прокси для обхода блокировок Telegram
# MTProto proxy to bypass Telegram blocking
[telegram.mtproto_proxy]
enabled = false
server = ""
port = 443
secret = ""
```

#### Задача 2.2: Добавить в Config класс
```python
# Telegram MTProto proxy
telegram_mtproto_proxy_enabled: bool = False
telegram_mtproto_proxy_server: str = ""
telegram_mtproto_proxy_port: int = 443
telegram_mtproto_proxy_secret: str = ""
```

---

### 🔧 ФАЗА 3: РЕАЛИЗАЦИЯ ФУНКЦИОНАЛА (по необходимости)
**Статус:** Можно отложить  
**Время:** ~1-2 дня  
**Риск:** НИЗКИЙ - улучшения

#### Задача 3.1: Реализовать chat_max_history_length
**Файлы:** `src/worker.py`, `src/telegram_client.py`  
**Описание:** Ограничить длину загружаемой истории чата

#### Задача 3.2: Реализовать tool_reminder_probability
**Файл:** `src/worker.py` или `src/tools.py`  
**Описание:** Случайно напоминать LLM о доступных инструментах

#### Задача 3.3: Реализовать video processing
**Файл:** Создать новый модуль `src/video_processor.py`  
**Описание:** Извлечение кадров из видео с учетом video_max_frames и video_min_step_ms

#### Задача 3.4: Реализовать wake_up_on_pinned_chat
**Файл:** `src/worker.py`  
**Описание:** Логика пробуждения при сообщениях в закреплённых чатах

---

## Чеклист выполнения

### Фаза 0 (критично):
- [ ] 0.1: Исправить чтение papik_name из конфига
- [ ] 0.2: Добавить can_write_to_a_new_person в Config класс
- [ ] 0.2: Добавить can_write_to_a_new_person в парсер
- [ ] 0.2: Добавить can_write_to_a_new_person в config.example.toml
- [ ] 0.3: Обновить config.toml
- [ ] ✅ Проверка: приложение запускается без ошибок
- [ ] ✅ Проверка: papik_name не пустая строка
- [ ] ✅ Проверка: proactive_service работает без AttributeError

### Фаза 1 (высокий приоритет):
- [ ] 1.1: Добавить [misc] секцию в config.example.toml
- [ ] 1.2: Добавить misc параметры в Config класс
- [ ] 1.3: Добавить парсинг misc параметров
- [ ] ✅ Проверка: все параметры читаются корректно

### Фаза 2 (низкий приоритет):
- [ ] 2.1: Добавить MTProto прокси в config.example.toml
- [ ] 2.2: Добавить MTProto прокси в Config класс
- [ ] 2.3: Добавить парсинг MTProto прокси
- [ ] ✅ Проверка: параметры присутствуют но не используются (заглушка)

### Фаза 3 (можно отложить):
- [ ] 3.1: Реализовать chat_max_history_length
- [ ] 3.2: Реализовать tool_reminder_probability
- [ ] 3.3: Реализовать video processing
- [ ] 3.4: Реализовать wake_up_on_pinned_chat

---

## Тестирование после Фазы 0

```bash
# 1. Проверить загрузку конфига
python -c "from src.config import load_config; cfg = load_config('config.toml'); print('Config loaded OK')"

# 2. Проверить papik_name
python -c "from src.config import load_config; cfg = load_config('config.toml'); assert cfg.papik_name != '', 'papik_name is empty!'; print(f'papik_name OK: {cfg.papik_name}')"

# 3. Проверить can_write_to_a_new_person
python -c "from src.config import load_config; cfg = load_config('config.toml'); assert hasattr(cfg, 'can_write_to_a_new_person'), 'Missing can_write_to_a_new_person'; print(f'can_write_to_a_new_person OK: {cfg.can_write_to_a_new_person}')"

# 4. Запустить приложение (smoke test)
python -m src.app
```

---

## Примечания

1. **Не удаляйте существующий функционал** - только добавляйте недостающие параметры
2. **Все изменения должны быть обратно совместимы** - старые конфиги должны работать
3. **Используйте default значения** из C++ kuni для новых параметров
4. **Комментарии в TOML** должны быть на русском и английском (как в существующих)
5. **После каждой фазы** - коммит в git с описанием изменений

## Ссылки
- Полный отчет: `docs/audit_report.md`
- Критичные баги: `docs/critical_fixes.md`
- C++ оригинал: `G:\AI\kuni\src\config.h`
