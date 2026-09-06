# kunipy

Python port of [kuni](https://github.com/alex2772/kuni) — LLM character AI with Telegram interface, RAG memory, and OpenAI-compatible proxy.

## Status

**Work in progress.** Currently implements:
- ✅ Configuration management with TOML (hot-reload)
- ✅ OpenAI-compatible chat/embedding client
- ✅ Diary memory system with RAG (vector search, sleep consolidation)
- ✅ Telegram client (mock implementation for testing)
- ✅ Tool system (function calling for LLM)
- ✅ Worker loop with LLM interaction
- ✅ Notification manager with priority queue
- ✅ Basic application orchestration

**Not yet implemented:**
- Real TDLib integration (requires pytdlib)
- Proxy server
- Stable Diffusion integration
- TTS (ElevenLabs/OpenAI)
- Web search
- Full Telegram event handling
- Prometheus metrics
- Working memory persistence

## Requirements

- Python 3.11+
- Dependencies listed in `pyproject.toml`

## Installation

```bash
# Clone the repository
cd C:/AI/kunipy

# Create virtual environment (optional)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e .
```

## Configuration

Create `config.toml` in the root directory. A default one will be generated on first run.

Minimal configuration:
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

## Running

```bash
python run.py
```

On first run with `telegram_enabled = true`, you'll be prompted to enter phone number and verification code.

## Architecture

- **config.py** — TOML configuration with hot-reload
- **openai_chat.py** — Async client for OpenAI-compatible APIs
- **diary.py** — Memory system with embeddings and RAG search
- **telegram_client.py** — Telegram client (pytdlib wrapper)
- **tools.py** — LLM function calling tools
- **notification_manager.py** — Priority queue for events
- **worker.py** — Worker that processes notifications with LLM
- **app.py** — Main application orchestration

## License

MIT
