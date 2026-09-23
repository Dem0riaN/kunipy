# Kunipy

**Kunipy is a Python-based AI character runtime with Telegram integration,
long-term memory, a configurable persona, autonomous background services, and
OpenAI-compatible interfaces.**

The project began from the ideas and some code of
[Alex2772/kuni](https://github.com/Alex2772/kuni), but it has since been
substantially reworked. Kunipy should be treated as an independent Python
project rather than as a simple Python port or a drop-in replacement for
`kuni`.

> **Status:** active development. The documentation describes the repository
> state reviewed on **2026-09-23**.

## Language

- [English](README.md)
- [Русский](README.ru.md)
- [简体中文](README.zh-CN.md)
- [日本語](README.ja.md)

## What it does

Kunipy currently provides the following major building blocks:

- Telegram client integration through TDLib / `aiotdlib`.
- OpenAI-compatible LLM chat and embedding clients.
- Editable character/persona prompts stored as Markdown.
- Long-term memory backed by ChromaDB and SQLite.
- Automatic memory extraction from recent conversations.
- Working memory for promises, plans, and short-lived context.
- Legacy Markdown diary storage and semantic diary retrieval.
- Automatic diary/context injection (Auto-RAG).
- Sleep/consolidation and proactive background services.
- Vision, speech recognition, text-to-speech, image generation, and web-search
  integrations where the corresponding external backend is configured.
- An OpenAI-compatible proxy with local tool execution.
- Prometheus-compatible LLM usage metrics.
- Optional desktop-character scaffolding with graceful degradation.

Not every capability is enabled by default, and several capabilities depend on
external services or optional components.

## Quick start

### Requirements

- Python **3.11+**.
- An OpenAI-compatible LLM endpoint.
- Telegram API credentials if Telegram is enabled.
- An embedding endpoint/model if the memory or diary retrieval paths are used.

Install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

On Windows:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

Create the configuration:

```bash
cp config.example.toml config.toml
```

Edit `config.toml`, then start:

```bash
python run.py
```

See:

- [`docs/installation.md`](docs/installation.md)
- [`docs/configuration.md`](docs/configuration.md)

## Documentation

| Topic | Document |
|---|---|
| Documentation index | [`docs/README.md`](docs/README.md) |
| Installation | [`docs/installation.md`](docs/installation.md) |
| Configuration | [`docs/configuration.md`](docs/configuration.md) |
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| Features | [`docs/features.md`](docs/features.md) |
| Memory and diary | [`docs/memory.md`](docs/memory.md) |
| OpenAI-compatible proxy | [`docs/proxy.md`](docs/proxy.md) |
| Testing | [`docs/testing.md`](docs/testing.md) |
| Project origin | [`docs/origins.md`](docs/origins.md) |
| Repository audit | [`docs/audit.md`](docs/audit.md) |

## Configuration model

The repository contains a large `config.example.toml`. It is the authoritative
configuration reference for the current codebase; the README deliberately
does not duplicate it.

Important sections include:

- `llm`
- `embedding`
- `telegram`
- `memory`
- `diary`
- `lockdown`
- `capabilities.*`
- `proxy`
- `worker`
- `metrics`
- `app`

Some historical configuration comments still describe features or names from
earlier implementation stages. See [`docs/configuration.md`](docs/configuration.md)
for the verified mapping.

## Architecture

Kunipy uses dependency injection and separates application orchestration,
domain models, interfaces, and infrastructure, but the repository still
contains legacy modules and compatibility code. The architecture should
therefore be understood as a **hybrid/refactored architecture**, not as a
perfectly isolated Clean Architecture implementation.

See [`docs/architecture.md`](docs/architecture.md).

## Relationship to `kuni`

Kunipy was originally created from work based on
[Alex2772/kuni](https://github.com/Alex2772/kuni).

It is no longer accurate to describe Kunipy simply as a Python port. The
current project contains substantial new Python architecture, memory,
character, diary, worker, proxy, and desktop-related work.

The provenance and licensing situation are documented separately in
[`docs/origins.md`](docs/origins.md).

## License

See [`LICENSE`](LICENSE).

Kunipy uses a project-specific free-distribution license with a no-sale
restriction and attribution requirements. Because the upstream `kuni`
repository did not contain a license at the time the work was started, the
license does not purport to grant rights over material belonging to the
upstream copyright holder.

## Disclaimer

Kunipy is software for experimentation and personal projects. External
services such as Telegram, LLM providers, embedding providers, TTS providers,
image-generation services, and search providers have their own terms and
licenses.
