# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — LLM character AI with Telegram interface, RAG memory, and OpenAI-compatible proxy.

Status
Implemented
✅ Real Telegram integration via aiotdlib
✅ LLM tool-calling loop
✅ Telegram messaging, editing, forwarding, reactions, and group administration
✅ Photo understanding (vision)
✅ Voice-message transcription (hearing)
✅ Text-to-speech / voice-message generation
✅ AI image generation via Stable Diffusion
✅ Web search via Ollama
✅ OpenAI-compatible proxy server
✅ Prometheus LLM usage metrics
✅ Working memory with persistence and TTL
✅ Character persona and system-prompt management
✅ Notification queue and worker system
✅ C++ kuni migration tool
✅ Diary storage, embeddings, semantic search, and sleep consolidation
Partially implemented / needs work
🟡 Diary memory ingestion — diary entries can be written internally, but there is currently no LLM tool for explicitly saving important memories. Most conversation data reaches the diary only when the conversation context is dumped after reaching the configured token limit.
🟡 Diary RAG — semantic search works, but memory quality depends heavily on the embedding endpoint and the current diary ingestion mechanism.
🟡 Sleep consolidation — implemented, but its usefulness is limited when the diary contains few automatically collected memories.
🟡 Vision — photo understanding is implemented; video-message frame extraction is not.
🟡 Optional capabilities — vision, hearing, TTS, web search, image generation, and proxy are disabled by default and require external backends and configuration.
🟡 Proxy streaming — streaming requests are handled internally, but responses are not emitted token-by-token.
Not implemented
❌ Video-message vision / frame extraction
❌ Dedicated LLM diary-write / memory-save tool
❌ Full parity with the original C++ kuni memory workflow
❌ Separate editable prompt files for all C++ prompts (system.md, anti_repeat.md, etc.)


## Requirements

- Python 3.11+
- Dependencies listed in `pyproject.toml` (installed via `pip install -e .`)
- A Telegram API ID/hash from [my.telegram.org](https://my.telegram.org)
- An OpenAI-compatible LLM endpoint (e.g. local Ollama, or a cloud provider)

## Installation

```bash
cd kunipy

# Create a virtual environment (required on most modern distros -- see PEP 668)
python3 -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on native Windows

# Install kunipy and all its dependencies
pip install -e .
```

## Configuration

`config.toml` in the project root holds all settings and supports
hot-reload (edit it while the app is running; changes are picked up
without a restart). A default file with bilingual (RU/EN) comments is
included in this repo — copy or edit it directly rather than starting
from scratch.

Minimal configuration:
`config.toml` is **never shipped** in this repo/archive — only `config.example.toml` is, purely for reference. This is intentional: `config.toml` holds your Telegram API credentials and other secrets, and shipping a same-named file alongside it would silently overwrite yours every time you re-download an update.

Run `python run.py` once with no `config.toml` present -- it will generate a default one next to itself and exit, asking you to fill it in. At minimum, set:

```toml
[general]
character_name = "Kuni"
character_nickname = "@kunii_chan"
papik_name = "YourName"
papik_chat_id = 123456789  # your Telegram user ID
telegram_api_id = 0        # get from my.telegram.org
telegram_api_hash = ""
telegram_enabled = true
lockdown = "papik_only"

[general.llm]
model = "deepseek-v4-flash"
[general.llm.endpoint]
base_url = "http://localhost:11434/v1/"

[general.embedding]
model = "qwen3-embedding"
[general.embedding.endpoint]
base_url = "http://localhost:11434/v1/"
```

If you're migrating from an existing C++ `kuni` install instead of starting fresh, see **Migrating from C++ kuni** below.

## Running

```bash
python run.py
```

Run it from the directory containing `config.toml` (paths for `data/`, `character_base.md`, `prompts/` are all relative to the current working directory). On first run with `telegram_enabled = true` and no existing session in `data/tdlib/`, aiotdlib will prompt you in the terminal for your phone number, the SMS/Telegram login code, and (if enabled) your 2FA password.

`character_base.md` and `character_appearance.md` are created next to `config.toml` on first run -- edit them freely, they're never overwritten afterward.

## Migrating from C++ kuni

If you already have a working C++ `kuni` install (diary entries, working memory, a logged-in TDLib session), use the migration tool instead of starting over:

```bash
python tools/migrate_from_cpp_kuni.py \
--source /path/to/kuni/build/bin \
--dest . \
--dry-run     # inspect first, then re-run without --dry-run
```

`--source` must point at the C++ binary's *actual runtime working directory* (typically `build/bin/` inside the kuni checkout), not the repository root. See the script's module docstring for exactly what gets converted and why (config key renames, diary metadata key renames, TDLib session reuse, etc.).

Because your kunipy `config.toml` will already exist by then, the migrated config is written to `config.toml.migrated` instead of overwriting yours -- diff and merge the two by hand (your kunipy config has extra sections like `[capabilities.proxy]` that don't exist in the C++ version).

## Architecture

- **config.py** — TOML configuration with hot-reload
- **openai_chat.py** — Async client for OpenAI-compatible APIs (chat, embeddings, vision, TTS, transcription)
- **diary.py** — Memory system with embeddings, RAG search, and sleep consolidation
- **telegram_client.py** — Telegram client (aiotdlib/TDLib wrapper)
- **character.py** — Character persona file management + system prompt building
- **tools.py** — LLM function-calling tools (Telegram actions, diary, media, web search, admin)
- **notification_manager.py** — Priority queue for events
- **worker.py** — Worker that processes notifications through the LLM tool-calling loop
- **proxy_server.py** — OpenAI-compatible proxy server (FastAPI)
- **metrics.py** — Prometheus metrics (`llm_usage_*`)
- **app.py** — Main application orchestration

## License

MIT
