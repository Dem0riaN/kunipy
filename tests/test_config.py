"""Tests for config.py: TOML parsing and defaults."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config, TTSBackend  # noqa: E402


def test_defaults():
    cfg = Config()
    assert cfg.character_name == "Kuni"
    assert cfg.proxy_enabled is False
    assert cfg.proxy_port == 10434
    assert cfg.diary_min_relatedness == 0.80


def test_from_toml_dict_general_section():
    data = {
        "general": {
            "character_name": "Miku",
            "character_nickname": "@miku_chan",
            "papik_name": "Someone",
            "papik_chat_id": 12345,
        },
    }
    cfg = Config.from_toml_dict(data)
    assert cfg.character_name == "Miku"
    assert cfg.character_nickname == "@miku_chan"
    assert cfg.papik_name == "Someone"
    assert cfg.papik_chat_id == 12345
    # Unspecified fields fall back to defaults.
    assert cfg.diary_min_relatedness == 0.80


def test_from_toml_dict_proxy_section():
    data = {
        "capabilities": {
            "proxy": {
                "enabled": True,
                "port": 12345,
                "upstream": {
                    "model": "gpt-x",
                    "endpoint": {"base_url": "http://example.com/v1", "bearer_key": "secret"},
                },
            },
        },
    }
    cfg = Config.from_toml_dict(data)
    assert cfg.proxy_enabled is True
    assert cfg.proxy_port == 12345
    assert cfg.proxy_upstream.model == "gpt-x"
    assert cfg.proxy_upstream.endpoint.base_url == "http://example.com/v1"
    assert cfg.proxy_upstream.endpoint.bearer_key == "secret"


def test_from_toml_dict_record_voice_backend():
    data = {"capabilities": {"record_voice": {"backend": "openai"}}}
    cfg = Config.from_toml_dict(data)
    assert cfg.record_voice_backend == TTSBackend.OPENAI


def test_from_toml_dict_telegram_phone():
    data = {"general": {"telegram_phone": "+1234567890"}}
    cfg = Config.from_toml_dict(data)
    assert cfg.telegram_phone == "+1234567890"


def test_from_toml_dict_missing_sections_uses_defaults():
    cfg = Config.from_toml_dict({})
    assert cfg == Config()
