# Installation

> This document describes the installation flow that should be checked against
> the current `pyproject.toml` and configuration before release.

## Requirements

- Python version declared by the current `pyproject.toml`
- Git
- Dependencies declared by the project

## Basic setup

```bash
git clone https://github.com/Dem0riaN/kunipy.git
cd kunipy

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuration

Start from the repository's current `config.example.toml` and create the
corresponding local configuration.

Do not copy configuration values blindly: credentials, API keys, Telegram
credentials, proxy settings, model paths and other environment-specific
settings must be supplied by the operator.

## Running

The repository currently uses `run.py` as its application entry point. Check
the current source and configuration before deploying it as a service.
