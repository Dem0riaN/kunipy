# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — LLM character AI with Telegram interface, RAG memory, and OpenAI-compatible proxy.

## Status

### Implemented

- ✅ Real TDLib integration via `aiotdlib`
- ✅ LLM tool-calling loop
  - Telegram actions
  - Diary search
  - Photo generation
  - Voice generation
  - Web search
  - Admin tools
- ✅ RAG diary with vector search
- ✅ Nightly sleep consolidation
- ✅ Vision — photo understanding
- ✅ Hearing — voice transcription
- ✅ Typing simulation
- ✅ Anti-repeat detection
- ✅ Working-memory persistence
- ✅ OpenAI-compatible proxy server
- ✅ Prometheus metrics (`llm_usage_*`) on port `9464`
- ✅ Migration from C++ `kuni` via `tools/migrate_from_cpp_kuni.py`

### Known gaps

- ⬜ Video-message vision (frame extraction) is not implemented
- ⬜ Proxy server streaming responses are not token-by-token (see `proxy_server.py` docstring)
- ⬜ 11 C++ prompt files (`system.md`, `anti_repeat.md`, etc.) are not yet wired up as separate editable files


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
