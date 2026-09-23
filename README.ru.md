# Kunipy

**Kunipy — Python-проект для запуска ИИ-персонажа с интеграцией Telegram,
долговременной памятью, настраиваемой персоной, фоновыми сервисами и
OpenAI-compatible интерфейсами.**

Проект начинался на основе идей и части кода
[Alex2772/kuni](https://github.com/Alex2772/kuni), но с тех пор был
существенно переработан. Сейчас Kunipy корректнее считать самостоятельным
Python-проектом, а не простым портом или drop-in replacement для `kuni`.

> **Состояние:** активная разработка. Документация ниже отражает ревизию
> репозитория на **23 сентября 2026 года**.

## Языки

- [English](README.md)
- [Русский](README.ru.md)
- [简体中文](README.zh-CN.md)
- [日本語](README.ja.md)

## Что умеет

Основные подсистемы текущей версии:

- интеграция с Telegram через TDLib / `aiotdlib`;
- OpenAI-compatible клиент для LLM и embeddings;
- редактируемая персона, хранящаяся в Markdown-файлах;
- долговременная память на базе ChromaDB + SQLite;
- автоматическое извлечение воспоминаний из диалогов;
- working memory для обещаний, планов и краткосрочного контекста;
- legacy-дневник в Markdown и семантический поиск по нему;
- автоматическая инъекция контекста дневника (Auto-RAG);
- фоновые worker/sleep/proactive-механизмы;
- vision, STT, TTS, генерация изображений и web search при наличии
  соответствующих backend'ов;
- OpenAI-compatible proxy с локальным выполнением инструментов;
- Prometheus-метрики использования LLM;
- экспериментальный desktop-character слой с graceful degradation.

Не все возможности включены по умолчанию. Часть из них требует внешних
сервисов или дополнительных компонентов.

## Быстрый запуск

Требуется Python **3.11+**.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.toml config.toml
python run.py
```

Далее настройте `config.toml`. Если включён Telegram, понадобятся API ID/hash
с [my.telegram.org](https://my.telegram.org/).

Подробности:

- [`docs/installation.md`](docs/installation.md)
- [`docs/configuration.md`](docs/configuration.md)

## Документация

| Тема | Документ |
|---|---|
| Индекс | [`docs/README.md`](docs/README.md) |
| Установка | [`docs/installation.md`](docs/installation.md) |
| Конфигурация | [`docs/configuration.md`](docs/configuration.md) |
| Архитектура | [`docs/architecture.md`](docs/architecture.md) |
| Возможности | [`docs/features.md`](docs/features.md) |
| Память и дневник | [`docs/memory.md`](docs/memory.md) |
| Proxy | [`docs/proxy.md`](docs/proxy.md) |
| Тестирование | [`docs/testing.md`](docs/testing.md) |
| Происхождение проекта | [`docs/origins.md`](docs/origins.md) |
| Ревизия | [`docs/audit.md`](docs/audit.md) |

## Происхождение

Изначально Kunipy создавался на основе
[Alex2772/kuni](https://github.com/Alex2772/kuni).

На текущем этапе называть его просто Python-портом уже некорректно:
архитектура, память, persona, diary, workers, proxy и desktop-направление
были существенно переработаны и расширены.

Отдельные сведения об авторстве и лицензировании вынесены в
[`docs/origins.md`](docs/origins.md).

## Лицензия

См. [`LICENSE`](LICENSE).

Используется специальная лицензия проекта с разрешением бесплатного
распространения, запретом продажи и обязательным указанием происхождения.

При этом upstream `kuni` на момент начала работ не содержал лицензии. Поэтому
файл `LICENSE` не пытается задним числом предоставить права на материалы,
которые принадлежат исходному правообладателю.
