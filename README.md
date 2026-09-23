# Kunipy

**Kunipy** is a Python-based AI character platform with persistent memory, personality, Telegram interaction, tools, multimodal capabilities, and an extensible application architecture.

The project originally started as a Python implementation inspired by [Kuni](https://github.com/Alex2772/kuni). It has since been substantially redesigned and expanded. The current codebase is an independent Python implementation; it does not contain the original Kuni C++ source code.

## Project status

| Area | Status |
|---|---|
| AI character / personality | ✅ Ready |
| OpenAI-compatible LLM client | ✅ Ready |
| LLM tool calling | ✅ Ready |
| Telegram integration | ✅ Ready |
| Persistent diary | ✅ Ready |
| Diary semantic search / RAG | ✅ Ready |
| Hybrid long-term memory | ✅ Ready |
| Automatic memory formation | ✅ Ready |
| Working memory | ✅ Ready |
| Sleep consolidation | ✅ Ready |
| Automatic diary RAG injection | ✅ Ready |
| Image understanding | ✅ Ready* |
| Voice transcription | ✅ Ready* |
| Text-to-speech / voice messages | ✅ Ready* |
| AI image generation | ✅ Ready* |
| Web search | ✅ Ready* |
| Stickers / reactions / message operations | ✅ Ready |
| Group administration tools | ✅ Ready* |
| OpenAI-compatible proxy | ✅ Ready |
| Prometheus metrics | ✅ Ready |
| Text document extraction | 🟡 Partial |
| Desktop character | 🚧 In progress |
| Live2D / desktop rendering | 🚧 In progress |
| Video-message frame extraction | 📋 Planned |
| More document/media extractors | 📋 Planned |

\* Requires the corresponding external backend and/or configuration.

For the detailed status and the distinction between implemented, partial, in-progress, and planned functionality, see [docs/status.md](docs/status.md).

## Highlights

- Editable AI character/personality prompts
- Telegram userbot integration through TDLib
- Persistent diary with embeddings and semantic retrieval
- Hybrid memory using ChromaDB + SQLite
- Automatic extraction of long-term memories from conversations
- Working memory for promises, plans, and pending context
- Sleep/consolidation processing
- Multimodal message processing
- Image generation through Stable Diffusion-compatible API
- Text-to-speech and voice-message generation
- Web search
- OpenAI-compatible proxy
- Prometheus usage metrics
- Extensible dependency-injection architecture

## Quick start

### Requirements

- Python 3.11+
- An OpenAI-compatible LLM endpoint
- Telegram API ID/hash if Telegram is enabled
- Additional providers/backends for optional capabilities

### Install

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
```

### Configure

Run:

```bash
python run.py
```

The application creates/loads its configuration according to the current configuration implementation. Use `config.example.toml` as the full configuration reference.

Never commit real credentials or API keys.

### Run

```bash
python run.py
```

See [docs/installation.md](docs/installation.md) and [docs/configuration.md](docs/configuration.md) for details.

## Documentation

- [Project status](docs/status.md)
- [Installation](docs/installation.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Features](docs/features.md)
- [Memory](docs/memory.md)
- [Proxy](docs/proxy.md)
- [Testing](docs/testing.md)
- [Origins and attribution](docs/origins.md)
- [Repository audit](docs/audit.md)

## Languages

- [Русский](README.ru.md)
- [中文](README.zh-CN.md)
- [日本語](README.ja.md)

## License

Kunipy is distributed under the custom license in [LICENSE](LICENSE).

The license permits free use, modification, and redistribution under its stated conditions, requires attribution, and prohibits selling the covered Kunipy materials.

Third-party dependencies, models, assets, and other external materials remain subject to their own licenses.
