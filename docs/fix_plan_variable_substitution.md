# План исправления: Variable Substitution в Working Memory

**Дата:** 2026-09-19  
**Проблема:** AttributeError при вызове _substitute_prompt_vars() с dict вместо Config

---

## Корневая причина

`_substitute_prompt_vars()` ожидает Config объект с атрибутами `.character_name`, но в `working_memory_update_service.py` передаётся dict.

**Ошибка:**
```
AttributeError: 'dict' object has no attribute 'character_name'
```

**Стектрейс:**
```
src/application/working_memory_update_service.py:131 → _substitute_prompt_vars()
src/prompt_loader.py:35 → config.character_name
```

---

## Сравнение с C++ оригиналом

### C++ kuni (important_things_to_remember.h:50)
```cpp
"- {}'s current emotional state: ...\n"
"- {}'s current physical state: ...\n"_format(config().characterName, config().characterName);
```
- **Прямая** подстановка через `_format()` во время построения промпта
- Переменные подставляются сразу, без отложенной замены

### Python kunipy (текущая реализация)
```python
# prompts/important_things_to_remember.md
"Focus on:
...
- **Physical state** — if relevant to {CHARACTER_NAME} as a character

Previous working memory (if any):
{previous_working_memory}"
```

**Проблема:** Python пытается передать кастомные переменные через dict, но функция их не понимает.

---

## Решение (без удаления функционала)

### Вариант 1: Расширить _substitute_prompt_vars() (РЕКОМЕНДУЕТСЯ)

**Файл:** `src/prompt_loader.py`

```python
def _substitute_prompt_vars(text: str, config=None, **custom_vars) -> str:
    """Replace ${CHARACTER_NAME}, ${PAPIK_NAME}, ${CHARACTER_NICKNAME} placeholders
    with actual config values.
    
    Args:
        text: Template text
        config: Config object OR dict with keys matching placeholder names
        **custom_vars: Additional variables for {key} placeholders
    
    Returns:
        Text with all variables substituted
    """
    if config is None:
        text_result = text
    elif isinstance(config, dict):
        # Dict mode: замена через ключи словаря
        text_result = text
        for key, value in config.items():
            text_result = text_result.replace(f"${{{key}}}", str(value))
            text_result = text_result.replace(f"{{{key}}}", str(value))
    else:
        # Config object mode: стандартные переменные
        text_result = text.replace("${CHARACTER_NAME}", config.character_name)
        text_result = text_result.replace("${CHARACTER_NICKNAME}", 
                                         config.character_nickname or config.character_name)
        text_result = text_result.replace("${PAPIK_NAME}", 
                                         config.papik_name or "your owner")
    
    # Custom variables (from **kwargs)
    for key, value in custom_vars.items():
        text_result = text_result.replace(f"{{{key}}}", str(value))
    
    return text_result
```

**Обратная совместимость:**
- ✅ Существующие вызовы с Config объектом работают как раньше
- ✅ Новые вызовы с dict работают корректно
- ✅ Поддержка кастомных переменных через **kwargs

---

### Вариант 2: Исправить вызов в working_memory_update_service.py

**Файл:** `src/application/working_memory_update_service.py`

```python
# Подстановка в два этапа
# 1. Стандартные переменные (CHARACTER_NAME)
prompt_with_config = _substitute_prompt_vars(
    self._prompt_template,
    self._config  # Config объект
)

# 2. Кастомные переменные (timespan, previous_working_memory)
prompt_with_vars = prompt_with_config.replace("{timespan}", timespan)
prompt_with_vars = prompt_with_vars.replace("{previous_working_memory}", 
                                            previous_wm_text or "(пусто)")
```

**Минус:** Двойная обработка строки, менее элегантно

---

## Рекомендация

**Использовать Вариант 1** — расширение `_substitute_prompt_vars()`:
1. ✅ Сохраняет весь существующий функционал
2. ✅ Добавляет гибкость (Config объект + dict + **kwargs)
3. ✅ Единая точка замены переменных
4. ✅ Соответствует SOLID (Open/Closed Principle)
5. ✅ Чистый код без дублирования логики

---

## Файлы для изменения

1. **src/prompt_loader.py**
   - Расширить `_substitute_prompt_vars()` для поддержки dict и **kwargs
   - Добавить проверку типа config
   - Сохранить обратную совместимость

2. **src/application/working_memory_update_service.py**
   - Изменить вызов `_substitute_prompt_vars()`:
     ```python
     prompt_with_vars = _substitute_prompt_vars(
         self._prompt_template,
         self._config,  # Config объект вместо dict
         timespan=timespan,
         previous_working_memory=previous_wm_text or "(пусто)",
     )
     ```

3. **prompts/important_things_to_remember.md**
   - Проверить синтаксис переменных: `{CHARACTER_NAME}` или `${CHARACTER_NAME}`
   - Убедиться что `{previous_working_memory}` и `{timespan}` используются корректно

---

## Тестирование

После исправления проверить:

```python
# Test 1: Config object (existing functionality)
from src.config import Config
from src.prompt_loader import _substitute_prompt_vars

cfg = Config()
cfg.character_name = "Kuni"
result = _substitute_prompt_vars("Hello {CHARACTER_NAME}!", cfg)
assert result == "Hello Kuni!"

# Test 2: Dict mode (new functionality)
result = _substitute_prompt_vars(
    "Hello {name}, today is {day}!",
    {"name": "Alex", "day": "Monday"}
)
assert result == "Hello Alex, today is Monday!"

# Test 3: Config + custom vars (combined)
result = _substitute_prompt_vars(
    "Hello {CHARACTER_NAME}, time: {timespan}",
    cfg,
    timespan="3 hours"
)
assert result == "Hello Kuni, time: 3 hours"
```

---

## Следующие шаги

1. ✅ Написать план (DONE)
2. ⏳ Реализовать расширенную версию `_substitute_prompt_vars()`
3. ⏳ Обновить вызов в `working_memory_update_service.py`
4. ⏳ Проверить совместимость с другими местами использования
5. ⏳ Запустить тесты
6. ⏳ Проверить работу на реальном диалоге

---

## Заметки

- ❌ НЕ УДАЛЯТЬ переменную `character_name` — она используется
- ✅ СОХРАНИТЬ весь существующий функционал
- ✅ ДОБАВИТЬ гибкость для кастомных переменных
- ✅ СЛЕДОВАТЬ SOLID принципам (OCP, SRP)
