# КРИТИЧНЫЕ ИСПРАВЛЕНИЯ - ТРЕБУЮТ НЕМЕДЛЕННОГО ВНИМАНИЯ

**Обновлено:** 2026-09-19  
**Статус:** ✅ Все критичные баги исправлены в v0.5.0-v0.6.0

## ✅ ИСПРАВЛЕНО: БАГ #1: papik_name не читается из конфига

**Проблема:**
- `papik_name` объявлен в `Config` классе (src/config.py:60)
- `papik_name` есть в config.example.toml и config.toml
- НО в парсере (src/config.py:242-246) НЕТ чтения этого параметра
- Результат: `papik_name` ВСЕГДА будет пустая строка ""

**Где используется:**
- prompt_loader.py - подстановка в промпты как {papik_name}
- character.py - использование в системных промптах

**Последствия:**
- Бот не будет правильно обращаться к владельцу
- Промпты будут содержать пустое имя вместо "Artellin"

**Исправление (ВЫПОЛНЕНО в v0.5.0):**
```python
# src/config.py строки 242-246
# Character
character = data.get("character", {})
cfg.character_name = character.get("name", cfg.character_name)
cfg.papik_name = character.get("papik_name", cfg.papik_name)  # ← ДОБАВЛЕНО
# Owner (papik) - read from [character] section
cfg.papik_chat_id = character.get("papik_chat_id", cfg.papik_chat_id)
```

---

## ✅ ИСПРАВЛЕНО: БАГ #2: can_write_to_a_new_person используется но не объявлен

**Проблема:**
- `can_write_to_a_new_person` ИСПОЛЬЗУЕТСЯ в коде:
  - src/application/proactive_service.py:215 - `if not self._deps.config.can_write_to_a_new_person`
- НО НЕТ в Config классе (src/config.py)
- НЕТ в config.example.toml
- НЕТ в config.toml

**Последствия:**
- AttributeError при запуске proactive_service
- Приложение упадет при попытке проактивно написать в чат

**Исправление (ВЫПОЛНЕНО в v0.5.0):**

### Шаг 1: Добавить в Config класс (src/config.py после строки 95):
```python
# Lockdown
lockdown: LockdownMode = LockdownMode.NONE
can_write_to_a_new_person: bool = False  # ← ДОБАВЛЕНО
```

### Шаг 2: Добавить в парсер (src/config.py после строки 285):
```python
# Lockdown
lockdown_cfg = data.get("lockdown", {})
mode_str = lockdown_cfg.get("mode", "none")
cfg.lockdown = LockdownMode(mode_str) if mode_str else LockdownMode.NONE
cfg.can_write_to_a_new_person = lockdown_cfg.get("can_write_to_a_new_person", cfg.can_write_to_a_new_person)  # ← ДОБАВЛЕНО
# papik_chat_id already loaded from top-level earlier
```

### Шаг 3: Добавить в config.example.toml (в секцию [lockdown]):
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

---

## ⚠️ ВЫСОКОПРИОРИТЕТНАЯ ПРОБЛЕМА: wake_up_on_pinned_chat отсутствует

**Проблема:**
- Параметр есть в C++ kuni (misc.wake_up_on_pinned_chat)
- Используется для того, чтобы закрепленные чаты могли будить бота (не только владелец)
- Полностью отсутствует в Python версии

**Рекомендация:**
Добавить аналогично can_write_to_a_new_person (средний приоритет, не критично).

---

## 📋 ПРОВЕРОЧНЫЙ ЧЕКЛИСТ

Перед запуском приложения проверить:

- [ ] papik_name читается из config.toml
- [ ] can_write_to_a_new_person объявлен в Config
- [ ] can_write_to_a_new_person читается из config.toml
- [ ] config.example.toml содержит оба параметра с комментариями
- [ ] Приложение запускается без AttributeError
- [ ] Промпты содержат корректное имя владельца (не пустую строку)

---

## 🔍 КАК ПРОВЕРИТЬ

### Проверка papik_name:
```python
from src.config import load_config
cfg = load_config("config.toml")
print(f"papik_name = '{cfg.papik_name}'")  # Должно быть "Artellin", а не ""
```

### Проверка can_write_to_a_new_person:
```python
from src.config import load_config
cfg = load_config("config.toml")
print(f"can_write_to_a_new_person = {cfg.can_write_to_a_new_person}")  # Не должно быть AttributeError
```

### Проверка в промптах:
```python
from src.prompt_loader import load_prompt
from src.config import load_config
cfg = load_config("config.toml")
prompt = load_prompt("system", config=cfg)
print("Papik name in prompt:", "Artellin" in prompt)  # Должно быть True
```
