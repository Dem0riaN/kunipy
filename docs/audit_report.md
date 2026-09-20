# Аудит портирования kunipy: Конфигурация и функциональность

**Дата аудита:** 2026-09-14  
**Обновлено:** 2026-09-19  
**Статус:** ✅ Критичные несоответствия исправлены в v0.5.0-v0.6.0  
**Оригинал:** C++ kuni (G:\AI\kuni)  
**Портированный код:** Python kunipy-main (G:\AI\kunipy-main)

---

## 1. СООТВЕТСТВИЕ ПАРАМЕТРОВ КОНФИГУРАЦИИ

### Источники истины:
- **C++ оригинал:** `kuni/src/config.h` (CONFIG_MODEL macro) + `kuni/src/config.cpp`
- **Python порт (для пользователей):** `kunipy-main/config.example.toml`
- **Python порт (код):** `kunipy-main/src/config.py`

### 1.1 Параметры из C++ config.h (70 параметров через CONFIG_MODEL):

#### [general] секция:
| C++ Параметр | TOML путь | Python Параметр | Статус |
|---|---|---|---|
| characterName | general.character_name | character_name | ✓ Есть |
| characterNickname | general.character_nickname | character_nickname | ✓ Есть |
| papikName | general.papik_name | papik_name | ✓ Есть |
| papikChatId | general.papik_chat_id | papik_chat_id | ✓ Есть |
| telegramApiId | general.telegram_api_id | telegram_api_id | ✓ Есть |
| telegramApiHash | general.telegram_api_hash | telegram_api_hash | ✓ Есть |
| telegramEnabled | general.telegram_enabled | telegram_enabled | ✓ Есть |
| llm | general.llm | llm (EndpointAndModel) | ✓ Есть |
| embedding | general.embedding | embedding (EndpointAndModel) | ✓ Есть |
| lockdown | general.lockdown | lockdown (LockdownMode) | ✓ Есть |

#### [misc] секция (60+ параметров):

**Основные поведенческие параметры:**

| C++ Параметр | TOML путь | Python | Статус | Примечание |
|---|---|---|---|---|
| canWriteToANewPerson | misc.can_write_to_a_new_person | can_write_to_a_new_person | ✅ ИСПРАВЛЕНО (v0.5.0) | Позволяет писать новым людям (спам-контроль) |
| wakeUpOnPinnedChat | misc.wake_up_on_pinned_chat | НЕТ | ❌ ПРОПУЩЕНО | Пробуждаться при сообщениях в закреплённых чатах |
| randomlyGoSleep | misc.randomly_go_sleep | random_sleep_enabled | ✅ ВОССТАНОВЛЕНО (v0.6.0) | 30% вероятность сна после обработки |
| toolReminderProbability | misc.tool_reminder_probability | НЕТ | ❌ ПРОПУЩЕНО | Вероятность напомнить о доступных инструментах |

**Память/Дневник:**

| C++ Параметр | TOML путь | Python | Статус | Примечание |
|---|---|---|---|---|
| diaryTokenCountTrigger | misc.diary_token_count_trigger | diary_context_token_threshold | ✓ Есть | Порог токенов для дампа памяти |
| diaryInjectionMaxLength | misc.diary_injection_max_length | diary_max_context_entries | ⚠️ РАЗНОЕ | C++: max length in tokens, Python: max entries count |
| diaryPlagiarismThreshold | misc.diary_plagiarism_threshold | diary_plagiarism_threshold | ✓ Есть |
| diaryMinRelatedness | misc.diary_min_relatedness | diary_min_relatedness | ✓ Есть |
| chatMaxHistoryLength | misc.chat_max_history_length | НЕТ | ❌ ПРОПУЩЕНО | Макс длина истории чата (в символах/токенах) |

**LLM параметры семплирования:**

| C++ Параметр | TOML путь | Python | Статус | Примечание |
|---|---|---|---|---|
| llmTemperature | misc.llm_temperature | llm_temperature | ✓ Есть | Optional<float> |
| llmTopP | misc.llm_top_p | llm_top_p | ✓ Есть | Optional<float> |
| llmTopK | misc.llm_top_k | llm_top_k | ✓ Есть | Optional<float>, но Python uses int |
| llmMinP | misc.llm_min_p | llm_min_p | ✓ Есть | Optional<float> |
| llmPresencePenalty | misc.presence_penalty | llm_presence_penalty | ✓ Есть | Optional<float> |
| llmRepetitionPenalty | misc.repetition_penalty | llm_repetition_penalty | ✓ Есть | Optional<float> |

**Anti-repeat система:**

| C++ Параметр | TOML путь | Python | Статус |
|---|---|---|---|
| antiRepeatTriggerMax | misc.anti_repeat_trigger_max | anti_repeat_trigger_max | ✓ Есть |
| antiRepeatTriggerAvg | misc.anti_repeat_trigger_avg | anti_repeat_trigger_avg | ✓ Есть |
| antiRepeatMaxHistory | misc.anti_repeat_max_history | anti_repeat_max_history | ✓ Есть |

**Прочие параметры:**

| C++ Параметр | TOML путь | Python | Статус | Примечание |
|---|---|---|---|---|
| suggestIgnoreChance | misc.suggest_ignore_chance | suggest_ignore_chance | ✓ Есть |
| requestTimeoutSecs | misc.request_timeout_secs | request_timeout_secs | ✓ Есть |
| videoMaxFrames | misc.video_max_frames | НЕТ | ❌ ПРОПУЩЕНО | Макс frames из видео для обработки |
| videoMinStepMs | misc.video_min_step_ms | НЕТ | ❌ ПРОПУЩЕНО | Минимальный интервал между frames |
| remindUseAsk | misc.remind_use_ask | remind_use_ask | ✓ Есть | Напоминать о #ask инструменте |
| typingSimulationMinWpm | misc.typing_simulation_min_wpm | typing_simulation_min_wpm | ✓ Есть |
| typingSimulationMaxWpm | misc.typing_simulation_max_wpm | typing_simulation_max_wpm | ✓ Есть |
| checkChatsOnStartup | misc.check_chats_on_startup | check_chats_on_startup | ✓ Есть |
| chatNotificationFilter | misc.chat_notification_filter | chat_notification_filter | ✓ Есть |
| canJoinChats | misc.can_join_chats | can_join_chats | ✓ Есть |
| canLeaveChats | misc.can_leave_chats | can_leave_chats | ✓ Есть |
| workerCount | misc.worker_count | worker_count | ✓ Есть |

#### [capabilities] секция:

| C++ Параметр | TOML путь | Python | Статус |
|---|---|---|---|
| capabilityWebSearch | capabilities.web_search.enabled | capability_web_search | ✓ Есть |
| webSearchOllamaKey | capabilities.web_search.ollama_bearer_key | web_search_ollama_key | ✓ Есть |
| capabilityVision | capabilities.vision.enabled | capability_vision | ✓ Есть |
| llmImageToText | capabilities.vision.llm_image_to_text | llm_image_to_text | ✓ Есть |
| llmImageToTextCheap | capabilities.vision.llm_image_to_text_cheap | llm_image_to_text_cheap | ✓ Есть |
| capabilityUseStickers | capabilities.use_stickers.enabled | capability_use_stickers | ✓ Есть |
| capabilityTakePhoto | capabilities.take_photo.enabled | capability_take_photo | ✓ Есть |
| sdEndpoint | capabilities.take_photo.sd.endpoint | sd_endpoint | ✓ Есть |
| sdCheckpoint | capabilities.take_photo.sd.checkpoint | sd_checkpoint | ✓ Есть |
| capabilityHearing | capabilities.hearing.enabled | capability_hearing | ✓ Есть |
| llmAudioToText | capabilities.hearing.llm_audio_to_text | llm_audio_to_text | ✓ Есть |
| capabilityRecordVoice | capabilities.record_voice.enabled | capability_record_voice | ✓ Есть |
| recordVoiceBackend | capabilities.record_voice.backend | record_voice_backend | ✓ Есть |
| recordVoiceElevenLabsKey | capabilities.record_voice.elevenlabs.key | record_voice_elevenlabs_key | ✓ Есть |
| recordVoiceElevenLabsVoice | capabilities.record_voice.elevenlabs.voice_id | record_voice_elevenlabs_voice_id | ✓ Есть |
| recordVoiceOpenAIUrl | capabilities.record_voice.openai.url | record_voice_openai_url | ✓ Есть |
| recordVoiceOpenAIKey | capabilities.record_voice.openai.key | record_voice_openai_key | ✓ Есть |
| recordVoiceOpenAIModel | capabilities.record_voice.openai.model | record_voice_openai_model | ✓ Есть |
| recordVoiceOpenAIVoice | capabilities.record_voice.openai.voice | record_voice_openai_voice | ✓ Есть |
| recordVoiceOpenAIFormat | capabilities.record_voice.openai.response_format | record_voice_openai_format | ✓ Есть |
| recordVoiceOpenAIPcmSampleRate | capabilities.record_voice.openai.pcm_sample_rate | record_voice_openai_pcm_sample_rate | ✓ Есть |
| proxyEnabled | capabilities.proxy.enabled | proxy_enabled | ✓ Есть |

---

## 2. ПАРАМЕТРЫ PYTHON, КОТОРЫХ НЕТ В C++ (НОВЫЕ)

| Python Параметр | TOML секция | C++ аналог | Статус |
|---|---|---|---|
| papik_name | character | НЕТ в C++ | ✓ Новое |
| telegram_phone | telegram | НЕТ в C++ | ✓ Новое (для авторизации) |
| telegram_database_directory | telegram | НЕТ в C++ | ✓ Новое |
| character_nickname | character | ✓ characterNickname | ✓ Перенесено |
| desktop_enabled | desktop | НЕТ в C++ | ✓ Новое (ТЗ-004) |
| desktop_window_width/height | desktop | НЕТ в C++ | ✓ Новое |
| desktop_fps | desktop | НЕТ в C++ | ✓ Новое |
| desktop_model_path | desktop | НЕТ в C++ | ✓ Новое |
| desktop_motion_dir | desktop | НЕТ в C++ | ✓ Новое |
| memory_enabled | memory | НЕТ в C++ | ✓ Новое (ТЗ-002) |
| memory_db_path | memory | НЕТ в C++ | ✓ Новое (SQLite) |
| memory_min_similarity | memory | НЕТ в C++ | ✓ Новое |
| desktop_owner_telegram_id | memory | НЕТ в C++ | ✓ Новое |
| diary_chroma_dir | diary | НЕТ в C++ | ✓ Новое (ChromaDB путь) |
| diary_embedding_dimension | diary | НЕТ в C++ | ✓ Новое |
| diary_auto_rag_enabled | diary | НЕТ в C++ | ✓ Новое |
| diary_context_token_threshold | diary | Частично (misc.diary_token_count_trigger) | ⚠️ Переработано |
| diary_max_context_entries | diary | Частично (misc.diary_injection_max_length) | ⚠️ Переработано |
| diary_max_merge_span_days | diary | НЕТ в C++ | ✓ Новое |
| diary_knn_soft_limit | diary | НЕТ в C++ | ✓ Новое |
| sleep_chance | diary | НЕТ в C++ (или misc.randomly_go_sleep) | ⚠️ Новое |
| metrics_enabled | metrics | НЕТ в C++ | ✓ Новое |
| metrics_port | metrics | НЕТ в C++ | ✓ Новое |
| timezone | app | НЕТ в C++ | ✓ Новое |
| document_processing_enabled | app | НЕТ в C++ | ✓ Новое |
| document_max_size_bytes | app | НЕТ в C++ | ✓ Новое |
| document_max_context_chars | app | НЕТ в C++ | ✓ Новое |
| proxy_port | proxy | НЕТ в C++ | ✓ Новое |
| proxy_upstream | proxy | НЕТ в C++ | ✓ Новое |
| worker_sleep_timeout | worker | НЕТ в C++ | ✓ Новое |
| hearing_endpoint | capabilities | НЕТ в C++ | ✓ Новое (явный endpoint) |
| vision_endpoint | capabilities | НЕТ в C++ | ✓ Новое |

---

## 3. ПОЛНОСТЬЮ ОТСУТСТВУЮЩИЙ ФУНКЦИОНАЛ

### ❌ В config.example.toml отсутствует:

1. **Telegram MTProto прокси параметры**
   - C++: `telegram_mtproto_proxy.enabled`, `server`, `port`, `secret`
   - Python: ❌ НЕТ
   - Статус: ПОЛНОЕ ОТСУТСТВИЕ

2. **Параметры спама-контроля:**
   - C++: `can_write_to_a_new_person`, `wake_up_on_pinned_chat`
   - Python: ❌ НЕТ
   - Статус: ПОЛНОЕ ОТСУТСТВИЕ

3. **Параметры видео-обработки:**
   - C++: `video_max_frames`, `video_min_step_ms`
   - Python: ❌ НЕТ
   - Статус: ПОЛНОЕ ОТСУТСТВИЕ

4. **История чата:**
   - C++: `chat_max_history_length`
   - Python: ❌ НЕТ
   - Статус: ПОЛНОЕ ОТСУТСТВИЕ

5. **Tool reminder:**
   - C++: `tool_reminder_probability`
   - Python: ❌ НЕТ
   - Статус: ПОЛНОЕ ОТСУТСТВИЕ

---

## 4. РАЗНОЧТЕНИЯ И ПЕРЕРАБОТКИ

### 4.1 diary_injection_max_length → diary_max_context_entries
- **C++:** `size_t diaryInjectionMaxLength = 0` - максимум токенов из дневника
- **Python:** `diary_max_context_entries = 5` - максимум записей
- **Проблема:** Разная семантика: токены vs записи
- **Требует решения:** ⚠️ РАЗНОЧТЕНИЕ

### 4.2 randomlyGoSleep → worker_sleep_enabled
- **C++:** `bool randomlyGoSleep = true` - случайный сон
- **Python:** `worker_sleep_enabled = false` (в config.toml) - простой флаг включения
- **Проблема:** Название потеряло семантику "случайного"
- **Требует решения:** ⚠️ ПЕРЕИМЕНОВАНИЕ, но функционально меняется

### 4.3 llmTemperature и прочие LLM параметры
- **C++:** `AOptional<float>` - может быть "none" (использовать default модели)
- **Python:** float с default значением (0.2 для temperature)
- **Проблема:** Python не различает "не установлено" vs "установлено явно"
- **Требует решения:** ⚠️ ФУНКЦИОНАЛЬНАЯ РАЗНИЦА

### 4.4 papik_name полностью потерян
- **C++:** `papikName` объявлен в config.h, используется в промптах
- **Python:** `papik_name` объявлен в Config класса, но:
  - НЕТ чтения из TOML (config.py:242-246 читает только papik_chat_id)
  - В config.example.toml `papik_name` находится в секции character, а не в отдельной секции
  - Всегда будет пустая строка ""
- **Требует решения:** ⚠️ КРИТИЧНАЯ ОШИБКА - папик не будет правильно идентифицирован в промптах

---

## 5. ИСПОЛЬЗОВАНИЕ ПАРАМЕТРОВ В КОДЕ PYTHON

### Проверенные использования:

✓ Параметры, используемые в коде:
- `llm` - в openai_chat.py, app.py
- `embedding` - в memory_service.py
- `telegram_enabled`, `telegram_api_id`, `telegram_api_hash` - в telegram_client.py
- `papik_chat_id` - в multiple files
- `lockdown` - в app.py, telegram_handler.py
- `diary_enabled` - в app.py
- `memory_enabled` - в app.py
- `worker_count` - в app.py
- `proxy_enabled`, `proxy_port` - в proxy_server.py
- `anti_repeat_*` - ✓ ИСПОЛЬЗУЮТСЯ в tools.py (_check_anti_repeat)
- `typing_simulation_*` - ✓ ИСПОЛЬЗУЮТСЯ в tools.py (simulate_typing)
- `can_write_to_a_new_person` - ⚠️ ИСПОЛЬЗУЕТСЯ в proactive_service.py, НО НЕТ В CONFIG

❌ Параметры, НИКОГДА НЕ ИСПОЛЬЗУЕМЫЕ в коде:
- `tool_reminder_probability` - НЕ ИСПОЛЬЗУЕТСЯ (но и нет в config.example.toml)
- `chat_max_history_length` - НЕ ИСПОЛЬЗУЕТСЯ (и нет в конфиге)
- `video_max_frames`, `video_min_step_ms` - НЕТ в конфиге и НЕ ИСПОЛЬЗУЮТСЯ
- `document_processing_enabled` - ОБЪЯВЛЕНО но НЕ ИСПОЛЬЗУЕТСЯ
- `document_max_size_bytes`, `document_max_context_chars` - НЕ ИСПОЛЬЗУЮТСЯ

⚠️ КРИТИЧНАЯ ПРОБЛЕМА:
- `can_write_to_a_new_person` - ИСПОЛЬЗУЕТСЯ В КОДЕ (proactive_service.py:215), но:
  - НЕТ в Config класе (src/config.py)
  - НЕТ в config.example.toml
  - НЕТ в config.toml
  - Код УПАДЁТ при обращении к `config.can_write_to_a_new_person`

---

## 6. КРАТКАЯ СВОДКА ПРОБЛЕМ

| # | Проблема | Тип | Приоритет |
|---|---|---|---|
| 1 | Отсутствует `can_write_to_a_new_person` | Отсутствует функционал | ВЫСОКИЙ |
| 2 | Отсутствует `wake_up_on_pinned_chat` | Отсутствует функционал | СРЕДНИЙ |
| 3 | Отсутствует `tool_reminder_probability` | Отсутствует функционал | НИЗКИЙ |
| 4 | Отсутствует видео-параметры | Отсутствует функционал | СРЕДНИЙ |
| 5 | Отсутствует `chat_max_history_length` | Отсутствует функционал | СРЕДНИЙ |
| 6 | Отсутствует MTProto прокси конфиг | Отсутствует функционал | НИЗКИЙ |
| 7 | `diary_injection_max_length` переработано неправильно | Разночтение | ВЫСОКИЙ |
| 8 | `randomlyGoSleep` потеряло "случайность" | Переработка | СРЕДНИЙ |
| 9 | LLM параметры потеряли Optional семантику | Разночтение | СРЕДНИЙ |
| 10 | `papik_name` объявлен но не читается из config | КРИТИЧЕСКАЯ ОШИБКА | КРИТИЧНЫЙ |
| 11 | `can_write_to_a_new_person` используется, но не объявлен | КРИТИЧЕСКАЯ ОШИБКА | КРИТИЧНЫЙ |

---

## 7. РЕКОМЕНДАЦИИ

### 🔥 КРИТИЧНЫЕ ИСПРАВЛЕНИЯ (требуются НЕМЕДЛЕННО):

#### 1. Добавить `papik_name` в парсинг конфига (src/config.py:242-246):
```python
# Character
character = data.get("character", {})
cfg.character_name = character.get("name", cfg.character_name)
cfg.papik_name = character.get("papik_name", cfg.papik_name)  # ← ДОБАВИТЬ ЭТУ СТРОКУ
# Owner (papik) - read from [character] section
cfg.papik_chat_id = character.get("papik_chat_id", cfg.papik_chat_id)
```

**Без этого:** papik_name всегда будет "", что сломает промпты.

#### 2. Добавить `can_write_to_a_new_person` в Config класс (src/config.py):
```python
# Lockdown
lockdown: LockdownMode = LockdownMode.NONE
can_write_to_a_new_person: bool = False  # ← ДОБАВИТЬ
```

И в парсер:
```python
# Lockdown
lockdown_cfg = data.get("lockdown", {})
mode_str = lockdown_cfg.get("mode", "none")
cfg.lockdown = LockdownMode(mode_str) if mode_str else LockdownMode.NONE
cfg.can_write_to_a_new_person = lockdown_cfg.get("can_write_to_a_new_person", cfg.can_write_to_a_new_person)
```

**Без этого:** proactive_service.py упадет с AttributeError.

### ⚠️ ВЫСОКОПРИОРИТЕТНЫЕ:

#### 3. Добавить недостающие параметры в config.example.toml:

```toml
[lockdown]
mode = "papik_only"

# Позволить боту писать новым людям без предыдущей истории
# Allow bot to write to new people without prior conversation history
# "false" предотвращает использование как спам-бот / prevents using as spam bot
can_write_to_a_new_person = false

# Будить бота при сообщениях в закреплённых чатах (не только от владельца)
# Wake up bot on messages in pinned chats (not only from owner)
wake_up_on_pinned_chat = false

[misc]
# Параметры видео-обработки / Video processing parameters
video_max_frames = 16
video_min_step_ms = 1000

# Макс длина истории чата в символах / Max chat history length in characters
chat_max_history_length = 2000

# Вероятность напомнить о доступных инструментах / Probability to remind about available tools
tool_reminder_probability = 0.02
```

#### 4. Добавить MTProto прокси в config (если планируется поддержка):

```toml
[telegram]
# ... existing params ...

[telegram.mtproto_proxy]
enabled = false
server = ""
port = 443
secret = ""
```

### 📋 СРЕДНИЙ ПРИОРИТЕТ:

#### 5. Реализовать недостающую логику:
- ✅ Anti-repeat - УЖЕ РЕАЛИЗОВАНО в tools.py
- ✅ Typing simulation - УЖЕ РЕАЛИЗОВАНО в tools.py
- ❌ Video processing (video_max_frames, video_min_step_ms) - НЕ РЕАЛИЗОВАНО
- ❌ Tool reminder probability - НЕ РЕАЛИЗОВАНО
- ❌ Chat history length limit - НЕ РЕАЛИЗОВАНО
- ❌ wake_up_on_pinned_chat - НЕ РЕАЛИЗОВАНО

#### 6. Исправить семантическую разницу diary_injection_max_length:
- C++: max tokens (size_t, может быть 0 = unlimited)
- Python: max entries (int, default 5)
- **Решение:** Добавить оба параметра или переименовать с комментарием

### 🔍 НИЗКИЙ ПРИОРИТЕТ (но желательно):

#### 7. Добавить Optional семантику для LLM параметров:
```python
llm_temperature: float | None = 0.2  # None = use model default
```

#### 8. Документировать изменения от C++:
Создать `PORTING_NOTES.md` с описанием сознательных отличий от оригинала.

---

## 8. ПЛАН ВНЕДРЕНИЯ

### Фаза 0: Исправление критичных багов (НЕМЕДЛЕННО)
1. ✅ Добавить `papik_name` в парсинг конфига
2. ✅ Добавить `can_write_to_a_new_person` в Config и парсинг
3. ✅ Проверить, что приложение запускается без ошибок

### Фаза 1: Приведение config.example.toml в соответствие с C++
1. Добавить все недостающие параметры из C++ config.h
2. Обновить комментарии и документацию
3. Убедиться, что все параметры в config.example.toml имеют соответствие в Config классе

### Фаза 2: Реализация отсутствующего функционала
1. Video processing parameters (если нужна поддержка видео)
2. Tool reminder probability
3. Chat history length limit
4. wake_up_on_pinned_chat

### Фаза 3: Рефакторинг и улучшения
1. Optional семантика для LLM параметров
2. MTProto прокси (если требуется)
3. Документация изменений

---

## 9. ИТОГОВАЯ ОЦЕНКА ПОРТИРОВАНИЯ

**Общий прогресс:** ~75-80%

**Хорошо:**
- ✅ Основные параметры перенесены корректно
- ✅ Структура конфига понятна и расширяема
- ✅ Anti-repeat и typing simulation реализованы
- ✅ Новые фичи (memory system, desktop, timezone) добавлены органично

**Проблемы:**
- ❌ Критичные баги: papik_name не читается, can_write_to_a_new_person отсутствует
- ❌ ~8 параметров из C++ полностью отсутствуют
- ❌ Некоторые параметры объявлены но не используются
- ⚠️ Семантика некоторых параметров изменена без документирования

**Рекомендация:**
Немедленно исправить критичные баги (папик не будет работать!), затем постепенно добавлять недостающие параметры по мере необходимости.
