# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — an LLM "character"
AI with a Telegram interface, RAG-based diary memory, and an
OpenAI-compatible proxy server.

## Status

**Feature-complete.** All components described in the original architecture
are implemented against real backends (no mocks in the request path):

- ✅ TOML configuration with hot-reload (`config.py`)
- ✅ Async OpenAI-compatible client — chat, streaming, embeddings,
  transcription, TTS, vision (`openai_chat.py`)
- ✅ Diary/RAG memory — markdown + JSON metadata, cosine similarity search,
  LLM-driven sleep consolidation (`diary.py`)
- ✅ Real Telegram client via `aiotdlib` — phone-number auth, sending,
  editing, forwarding, reacting, deleting, searching, stickers, photos,
  voice messages, group admin actions (`telegram_client.py`)
- ✅ Tool system (LLM function calling) wired to real handlers: web search,
  text-to-speech, image generation, group admin, chat membership
  (`tools.py`)
- ✅ Worker loop that processes notifications, calls the LLM, and dispatches
  tool calls (`worker.py`)
- ✅ Priority-queue notification manager (`notification_manager.py`)
- ✅ In-memory working memory with TTL (`working_memory.py`)
- ✅ Stable Diffusion image generation, with a placeholder-image fallback
  when no SD endpoint is configured (`image_generator.py`)
- ✅ OpenAI-compatible proxy server (FastAPI) — intercepts
  `/v1/chat/completions` to inject the character/persona and a reduced
  tool set, passes every other `/v1/*` route through to the upstream
  endpoint unmodified (`proxy_server.py`)
- ✅ Prometheus metrics — token usage broken down by model/chat/call site,
  served on port 9464 (`metrics.py`)
- ✅ Character persona files, generated with sensible defaults on first run
  and never overwritten again (`character.py`)
- ✅ Main application orchestration — Telegram event handling, proactive
  messages, worker/proxy/metrics startup (`app.py`)
- ✅ Migration tool for importing an existing C++ `kuni` working directory
  (config, prompts, diary, working memory, TDLib session) (`tools/migrate_from_cpp_kuni.py`)
- ✅ Test suite covering config, diary, character, tools, worker,
  notification manager, working memory, openai client, proxy server, and
  the migration tool (`tests/`)

**Known simplifications / things to be aware of, not "missing":**
- If no Stable Diffusion endpoint is configured, `take_photo` returns a
  small placeholder image instead of failing — this is an intentional
  graceful-degradation default, not a stub.
- The proxy server's streaming mode runs the full tool-calling loop
  internally and then emits the final answer as a single SSE chunk
  (rather than token-by-token upstream streaming). This is a deliberate
  simplification: clients that only care about the final text see no
  difference.
- Vision (image understanding) and audio transcription ("hearing") are
  implemented in `openai_chat.py` but are opt-in via
  `[capabilities.vision]` / `[capabilities.hearing]` in `config.toml`,
  same as every other capability.

If you find something genuinely broken or unimplemented, please open an
issue — the list above reflects a source-level review, not a promise that
every code path is bug-free.

## Requirements

- Python 3.11+
- Dependencies listed in `pyproject.toml` (installed via `pip install -e .`)
- Optional, depending on which capabilities you enable in `config.toml`:
  an Ollama (or other OpenAI-compatible) endpoint for chat/embeddings, a
  Stable Diffusion WebUI endpoint for `take_photo`, an ElevenLabs or
  OpenAI TTS key for `record_audio`, and an Ollama web-search API key.

## Installation

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e .
# or, for running the test suite too:
pip install -e ".[dev]"
```

## Configuration

`config.toml` in the project root holds all settings and supports
hot-reload (edit it while the app is running; changes are picked up
without a restart). A default file with bilingual (RU/EN) comments is
included in this repo — copy or edit it directly rather than starting
from scratch.

Minimal configuration:

```toml
[general]
character_name = "Kuni"
character_nickname = "@kunii_chan"
telegram_api_id = 0        # get from my.telegram.org
telegram_api_hash = ""
telegram_enabled = true
telegram_phone = ""        # leave empty to be prompted on first run

[general.llm]
model = "deepseek-v4-flash"
[general.llm.endpoint]
base_url = "http://localhost:11434/v1/"

[general.embedding]
model = "qwen3-embedding"
[general.embedding.endpoint]
base_url = "http://localhost:11434/v1/"
```

Optional capabilities (web search, vision, stickers, image generation,
audio transcription, TTS, the OpenAI-compatible proxy server) are each
disabled by default and turned on individually under `[capabilities.*]`
in `config.toml`. See the shipped `config.toml` for the full set of
options and inline documentation.

### Migrating from the original C++ `kuni`

If you have an existing C++ `kuni` working directory (config, diary,
`working_memory.md`, TDLib session), you can import it instead of
starting fresh:

```bash
python tools/migrate_from_cpp_kuni.py --source /path/to/kuni/build/bin --dest .
```

Add `--dry-run` to preview what would be copied/converted without writing
anything. See `python tools/migrate_from_cpp_kuni.py --help` for all
options (e.g. `--strip-embeddings` if you're switching embedding models).

## Running

```bash
python run.py
```

On first run with `telegram_enabled = true`, you'll be prompted for your
phone number and the verification code sent by Telegram. Character
persona files (`character_base.md`, `character_appearance.md`) are
generated with sensible defaults on first run under `prompts/` — edit
them and restart to pick up changes.

If `[capabilities.proxy]` is enabled, an OpenAI-compatible server also
starts on the configured port, so any OpenAI-client-compatible tool
(IDE plugins, scripts, etc.) can talk to it directly.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

| File | Responsibility |
|---|---|
| `config.py` | TOML configuration, hot-reload, typed access |
| `openai_chat.py` | Async client for OpenAI-compatible APIs: chat, streaming, embeddings, transcription, TTS, vision |
| `diary.py` | RAG memory: markdown + JSON metadata, cosine search, sleep consolidation |
| `character.py` | Persona/system-prompt files, generated on first run |
| `telegram_client.py` | Real Telegram client (`aiotdlib`), messaging, media, group admin |
| `tools.py` | LLM function-calling tools and their real handlers |
| `notification_manager.py` | Priority queue for incoming events |
| `working_memory.py` | In-memory key/value store with TTL |
| `image_generator.py` | Stable Diffusion wrapper, with placeholder fallback |
| `worker.py` | Processes notifications, calls the LLM, dispatches tool calls |
| `proxy_server.py` | OpenAI-compatible FastAPI proxy with persona injection and tool-calling loop |
| `metrics.py` | Prometheus metrics (LLM token usage) |
| `app.py` | Main orchestration: Telegram events, workers, proxy, metrics startup |
| `tools/migrate_from_cpp_kuni.py` | One-off migration from a C++ `kuni` working directory |

## License

MIT
