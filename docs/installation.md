# Installation

## Requirements

The package metadata currently declares:

- Python `>=3.11`
- `aiohttp`
- `tomli`
- `tomli-w`
- `sentence-transformers`
- `chromadb`
- `fastapi`
- `uvicorn`
- `python-dotenv`
- `watchdog`
- `numpy`
- `aiotdlib`
- `prometheus_client`

Development dependencies include `pytest`, `pytest-asyncio`, `httpx`, and
`ruff`.

These requirements are taken from `pyproject.toml`, not from the old README.

## Install

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Configuration

Copy the example:

```bash
cp config.example.toml config.toml
```

Then configure at least the LLM endpoint/model. If Telegram is enabled, also
configure:

- `telegram.api_id`
- `telegram.api_hash`
- optionally `telegram.phone`

Telegram credentials are obtained from Telegram's developer portal.

## Start

The documented entry point is:

```bash
python run.py
```

The application loads `config.toml`, creates the dependency graph and starts
the enabled services.

## First Telegram login

When TDLib needs authentication, the Telegram client may request:

1. phone number;
2. login code;
3. two-factor authentication password, if enabled.

The exact interaction is handled by `aiotdlib`/TDLib.

## Character files

The character implementation creates editable Markdown files when they do not
exist. The current implementation documents:

- `character_base.md`
- `character_appearance.md`

Existing files are not overwritten on startup.

## Runtime data

Depending on enabled features, runtime state is stored under directories such
as:

- `data/`
- `diary/`
- Telegram's configured database directory;
- ChromaDB persistence directories;
- proxy logs/data.

Do not commit credentials, Telegram sessions, databases, or generated private
character data.
