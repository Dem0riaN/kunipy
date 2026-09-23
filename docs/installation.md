# Installation

## Requirements

- Python 3.11+
- Git
- An OpenAI-compatible LLM endpoint
- Telegram API ID/hash if Telegram is enabled

Optional capabilities require their respective external services/backends.

## Install

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
```

## Configure

Start the application once to create/load the local configuration:

```bash
python run.py
```

Use `config.example.toml` as the full reference.

Do not commit API keys, Telegram credentials, bearer tokens or other secrets.

## Run

```bash
python run.py
```

If Telegram is enabled and no existing authorized session is available, TDLib/aiotdlib performs the interactive authorization flow. citeturn13view1
