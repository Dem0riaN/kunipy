"""Configuration management for kunipy.

Reads and parses config.toml, supports hot-reloading, provides typed access.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import tomli
import tomli_w


class LockdownMode(Enum):
    """Lockdown modes for restricting access."""
    NONE = "none"
    CONTACTS_ONLY = "contacts_only"
    PAPIK_ONLY = "papik_only"


class TTSBackend(Enum):
    """TTS backend selection."""
    ELEVENLABS = "elevenlabs"
    OPENAI = "openai"


@dataclass
class Endpoint:
    """HTTP endpoint with optional bearer token."""
    base_url: str = ""
    bearer_key: str = ""


@dataclass
class EndpointAndModel:
    """Endpoint with a specific model name."""
    endpoint: Endpoint = field(default_factory=Endpoint)
    model: str = ""


@dataclass
class Config:
    """Main configuration container."""

    # general
    character_name: str = "Kuni"
    character_nickname: str = "@kunii_chan"
    papik_name: str = "Alex2772"
    papik_chat_id: int = 625207005
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_enabled: bool = True
    llm: EndpointAndModel = field(default_factory=lambda: EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="deepseek-v4-flash"
    ))
    embedding: EndpointAndModel = field(default_factory=lambda: EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="qwen3-embedding"
    ))
    lockdown: LockdownMode = LockdownMode.PAPIK_ONLY

    # misc
    can_write_to_a_new_person: bool = False
    wake_up_on_pinned_chat: bool = False
    randomly_go_sleep: bool = True
    tool_reminder_probability: float = 0.02
    diary_token_count_trigger: int = 40000
    diary_injection_max_length: int = 0
    diary_plagiarism_threshold: float = 0.97
    diary_min_relatedness: float = 0.80
    chat_max_history_length: int = 2000
    llm_temperature: Optional[float] = 0.2
    llm_top_p: Optional[float] = None
    llm_top_k: Optional[float] = None
    llm_min_p: Optional[float] = None
    llm_presence_penalty: Optional[float] = None
    llm_repetition_penalty: Optional[float] = None
    anti_repeat_trigger_max: float = 0.95
    anti_repeat_trigger_avg: float = 0.85
    anti_repeat_max_history: int = 32
    suggest_ignore_chance: float = 0.1
    request_timeout_secs: int = 30
    video_max_frames: int = 16
    video_min_step_ms: int = 1000
    remind_use_ask: bool = True
    typing_simulation_min_wpm: int = 120
    typing_simulation_max_wpm: int = 150
    check_chats_on_startup: bool = True
    chat_notification_filter: LockdownMode = LockdownMode.NONE
    can_join_chats: bool = False
    can_leave_chats: bool = True
    worker_count: int = 1

    # capabilities
    capability_web_search: bool = False
    web_search_ollama_key: str = ""
    capability_vision: bool = False
    llm_image_to_text: EndpointAndModel = field(default_factory=lambda: EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="qwen3.5:9b"
    ))
    llm_image_to_text_cheap: EndpointAndModel = field(default_factory=lambda: EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:11434/v1/"),
        model="ministral-3:8b"
    ))
    capability_use_stickers: bool = False
    capability_take_photo: bool = False
    sd_endpoint: Endpoint = field(default_factory=lambda: Endpoint(base_url="http://localhost:7860/"))
    sd_checkpoint: str = "novaAnimeXL_ilV170.safetensors"
    capability_hearing: bool = False
    llm_audio_to_text: EndpointAndModel = field(default_factory=lambda: EndpointAndModel(
        endpoint=Endpoint(base_url="http://localhost:9000/v1/"),
        model="base"
    ))
    capability_record_voice: bool = False
    record_voice_backend: TTSBackend = TTSBackend.ELEVENLABS
    record_voice_elevenlabs_key: str = ""
    record_voice_elevenlabs_voice: str = "pPdl9cQBQq4p6mRkZy2Z"
    record_voice_openai_url: str = "https://api.openai.com/v1/"
    record_voice_openai_key: str = ""
    record_voice_openai_model: str = "tts-1"
    record_voice_openai_voice: str = "alloy"
    record_voice_openai_format: str = "mp3"
    record_voice_openai_pcm_sample_rate: int = 24000

    # proxy
    proxy_enabled: bool = False

    @classmethod
    def from_toml_dict(cls, data: dict[str, Any]) -> "Config":
        """Parse TOML dict into Config instance."""
        cfg = cls()

        general = data.get("general", {})
        cfg.character_name = general.get("character_name", cfg.character_name)
        cfg.character_nickname = general.get("character_nickname", cfg.character_nickname)
        cfg.papik_name = general.get("papik_name", cfg.papik_name)
        cfg.papik_chat_id = general.get("papik_chat_id", cfg.papik_chat_id)
        cfg.telegram_api_id = general.get("telegram_api_id", cfg.telegram_api_id)
        cfg.telegram_api_hash = general.get("telegram_api_hash", cfg.telegram_api_hash)
        cfg.telegram_enabled = general.get("telegram_enabled", cfg.telegram_enabled)
        if "llm" in general:
            llm = general["llm"]
            cfg.llm.model = llm.get("model", cfg.llm.model)
            if "endpoint" in llm:
                cfg.llm.endpoint.base_url = llm["endpoint"].get("base_url", cfg.llm.endpoint.base_url)
                cfg.llm.endpoint.bearer_key = llm["endpoint"].get("bearer_key", cfg.llm.endpoint.bearer_key)
        if "embedding" in general:
            emb = general["embedding"]
            cfg.embedding.model = emb.get("model", cfg.embedding.model)
            if "endpoint" in emb:
                cfg.embedding.endpoint.base_url = emb["endpoint"].get("base_url", cfg.embedding.endpoint.base_url)
                cfg.embedding.endpoint.bearer_key = emb["endpoint"].get("bearer_key", cfg.embedding.endpoint.bearer_key)
        cfg.lockdown = LockdownMode(general.get("lockdown", cfg.lockdown.value))

        misc = data.get("misc", {})
        cfg.can_write_to_a_new_person = misc.get("can_write_to_a_new_person", cfg.can_write_to_a_new_person)
        cfg.wake_up_on_pinned_chat = misc.get("wake_up_on_pinned_chat", cfg.wake_up_on_pinned_chat)
        cfg.randomly_go_sleep = misc.get("randomly_go_sleep", cfg.randomly_go_sleep)
        cfg.tool_reminder_probability = misc.get("tool_reminder_probability", cfg.tool_reminder_probability)
        cfg.diary_token_count_trigger = misc.get("diary_token_count_trigger", cfg.diary_token_count_trigger)
        cfg.diary_injection_max_length = misc.get("diary_injection_max_length", cfg.diary_injection_max_length)
        cfg.diary_plagiarism_threshold = misc.get("diary_plagiarism_threshold", cfg.diary_plagiarism_threshold)
        cfg.diary_min_relatedness = misc.get("diary_min_relatedness", cfg.diary_min_relatedness)
        cfg.chat_max_history_length = misc.get("chat_max_history_length", cfg.chat_max_history_length)
        cfg.llm_temperature = misc.get("llm_temperature", cfg.llm_temperature)
        cfg.llm_top_p = misc.get("llm_top_p", cfg.llm_top_p)
        cfg.llm_top_k = misc.get("llm_top_k", cfg.llm_top_k)
        cfg.llm_min_p = misc.get("llm_min_p", cfg.llm_min_p)
        cfg.llm_presence_penalty = misc.get("presence_penalty", cfg.llm_presence_penalty)
        cfg.llm_repetition_penalty = misc.get("repetition_penalty", cfg.llm_repetition_penalty)
        cfg.anti_repeat_trigger_max = misc.get("anti_repeat_trigger_max", cfg.anti_repeat_trigger_max)
        cfg.anti_repeat_trigger_avg = misc.get("anti_repeat_trigger_avg", cfg.anti_repeat_trigger_avg)
        cfg.anti_repeat_max_history = misc.get("anti_repeat_max_history", cfg.anti_repeat_max_history)
        cfg.suggest_ignore_chance = misc.get("suggest_ignore_chance", cfg.suggest_ignore_chance)
        cfg.request_timeout_secs = misc.get("request_timeout_secs", cfg.request_timeout_secs)
        cfg.video_max_frames = misc.get("video_max_frames", cfg.video_max_frames)
        cfg.video_min_step_ms = misc.get("video_min_step_ms", cfg.video_min_step_ms)
        cfg.remind_use_ask = misc.get("remind_use_ask", cfg.remind_use_ask)
        cfg.typing_simulation_min_wpm = misc.get("typing_simulation_min_wpm", cfg.typing_simulation_min_wpm)
        cfg.typing_simulation_max_wpm = misc.get("typing_simulation_max_wpm", cfg.typing_simulation_max_wpm)
        cfg.check_chats_on_startup = misc.get("check_chats_on_startup", cfg.check_chats_on_startup)
        cfg.chat_notification_filter = LockdownMode(misc.get("chat_notification_filter", cfg.chat_notification_filter.value))
        cfg.can_join_chats = misc.get("can_join_chats", cfg.can_join_chats)
        cfg.can_leave_chats = misc.get("can_leave_chats", cfg.can_leave_chats)
        cfg.worker_count = misc.get("worker_count", cfg.worker_count)

        capabilities = data.get("capabilities", {})
        cfg.capability_web_search = capabilities.get("web_search", {}).get("enabled", cfg.capability_web_search)
        cfg.web_search_ollama_key = capabilities.get("web_search", {}).get("ollama_bearer_key", cfg.web_search_ollama_key)
        cfg.capability_vision = capabilities.get("vision", {}).get("enabled", cfg.capability_vision)
        vision = capabilities.get("vision", {})
        if "llm_image_to_text" in vision:
            cfg.llm_image_to_text.model = vision["llm_image_to_text"].get("model", cfg.llm_image_to_text.model)
            if "endpoint" in vision["llm_image_to_text"]:
                cfg.llm_image_to_text.endpoint.base_url = vision["llm_image_to_text"]["endpoint"].get("base_url", cfg.llm_image_to_text.endpoint.base_url)
                cfg.llm_image_to_text.endpoint.bearer_key = vision["llm_image_to_text"]["endpoint"].get("bearer_key", cfg.llm_image_to_text.endpoint.bearer_key)
        if "llm_image_to_text_cheap" in vision:
            cfg.llm_image_to_text_cheap.model = vision["llm_image_to_text_cheap"].get("model", cfg.llm_image_to_text_cheap.model)
            if "endpoint" in vision["llm_image_to_text_cheap"]:
                cfg.llm_image_to_text_cheap.endpoint.base_url = vision["llm_image_to_text_cheap"]["endpoint"].get("base_url", cfg.llm_image_to_text_cheap.endpoint.base_url)
                cfg.llm_image_to_text_cheap.endpoint.bearer_key = vision["llm_image_to_text_cheap"]["endpoint"].get("bearer_key", cfg.llm_image_to_text_cheap.endpoint.bearer_key)
        cfg.capability_use_stickers = capabilities.get("use_stickers", {}).get("enabled", cfg.capability_use_stickers)
        cfg.capability_take_photo = capabilities.get("take_photo", {}).get("enabled", cfg.capability_take_photo)
        take_photo = capabilities.get("take_photo", {})
        if "sd" in take_photo:
            sd = take_photo["sd"]
            cfg.sd_endpoint.base_url = sd.get("endpoint", {}).get("base_url", cfg.sd_endpoint.base_url)
            cfg.sd_endpoint.bearer_key = sd.get("endpoint", {}).get("bearer_key", cfg.sd_endpoint.bearer_key)
            cfg.sd_checkpoint = sd.get("checkpoint", cfg.sd_checkpoint)
        cfg.capability_hearing = capabilities.get("hearing", {}).get("enabled", cfg.capability_hearing)
        hearing = capabilities.get("hearing", {})
        if "llm_audio_to_text" in hearing:
            cfg.llm_audio_to_text.model = hearing["llm_audio_to_text"].get("model", cfg.llm_audio_to_text.model)
            if "endpoint" in hearing["llm_audio_to_text"]:
                cfg.llm_audio_to_text.endpoint.base_url = hearing["llm_audio_to_text"]["endpoint"].get("base_url", cfg.llm_audio_to_text.endpoint.base_url)
                cfg.llm_audio_to_text.endpoint.bearer_key = hearing["llm_audio_to_text"]["endpoint"].get("bearer_key", cfg.llm_audio_to_text.endpoint.bearer_key)
        cfg.capability_record_voice = capabilities.get("record_voice", {}).get("enabled", cfg.capability_record_voice)
        record_voice = capabilities.get("record_voice", {})
        cfg.record_voice_backend = TTSBackend(record_voice.get("backend", cfg.record_voice_backend.value))
        cfg.record_voice_elevenlabs_key = record_voice.get("elevenlabs", {}).get("key", cfg.record_voice_elevenlabs_key)
        cfg.record_voice_elevenlabs_voice = record_voice.get("elevenlabs", {}).get("voice_id", cfg.record_voice_elevenlabs_voice)
        openai_tts = record_voice.get("openai", {})
        cfg.record_voice_openai_url = openai_tts.get("url", cfg.record_voice_openai_url)
        cfg.record_voice_openai_key = openai_tts.get("key", cfg.record_voice_openai_key)
        cfg.record_voice_openai_model = openai_tts.get("model", cfg.record_voice_openai_model)
        cfg.record_voice_openai_voice = openai_tts.get("voice", cfg.record_voice_openai_voice)
        cfg.record_voice_openai_format = openai_tts.get("response_format", cfg.record_voice_openai_format)
        cfg.record_voice_openai_pcm_sample_rate = openai_tts.get("pcm_sample_rate", cfg.record_voice_openai_pcm_sample_rate)

        cfg.proxy_enabled = capabilities.get("proxy", {}).get("enabled", cfg.proxy_enabled)

        return cfg


_CONFIG: Optional[Config] = None
_CONFIG_PATH: Optional[Path] = None


def load_config(config_path: str | Path = "config.toml") -> Config:
    """Load config from TOML file."""
    global _CONFIG_PATH, _CONFIG
    _CONFIG_PATH = Path(config_path)

    if not _CONFIG_PATH.exists():
        # Create default config
        _CONFIG = Config()
        save_config(_CONFIG, _CONFIG_PATH)
        print(f"Created default config at {_CONFIG_PATH}", file=sys.stderr)
        print("Please populate it and restart.", file=sys.stderr)
        sys.exit(1)

    with open(_CONFIG_PATH, "rb") as f:
        data = tomli.load(f)

    _CONFIG = Config.from_toml_dict(data)
    return _CONFIG


def save_config(cfg: Config, path: Path) -> None:
    """Save config to TOML file."""
    data: dict[str, Any] = {
        "general": {
            "character_name": cfg.character_name,
            "character_nickname": cfg.character_nickname,
            "papik_name": cfg.papik_name,
            "papik_chat_id": cfg.papik_chat_id,
            "telegram_api_id": cfg.telegram_api_id,
            "telegram_api_hash": cfg.telegram_api_hash,
            "telegram_enabled": cfg.telegram_enabled,
            "lockdown": cfg.lockdown.value,
            "llm": {
                "model": cfg.llm.model,
                "endpoint": {
                    "base_url": cfg.llm.endpoint.base_url,
                    "bearer_key": cfg.llm.endpoint.bearer_key,
                }
            },
            "embedding": {
                "model": cfg.embedding.model,
                "endpoint": {
                    "base_url": cfg.embedding.endpoint.base_url,
                    "bearer_key": cfg.embedding.endpoint.bearer_key,
                }
            },
        },
        "misc": {
            "can_write_to_a_new_person": cfg.can_write_to_a_new_person,
            "wake_up_on_pinned_chat": cfg.wake_up_on_pinned_chat,
            "randomly_go_sleep": cfg.randomly_go_sleep,
            "tool_reminder_probability": cfg.tool_reminder_probability,
            "diary_token_count_trigger": cfg.diary_token_count_trigger,
            "diary_injection_max_length": cfg.diary_injection_max_length,
            "diary_plagiarism_threshold": cfg.diary_plagiarism_threshold,
            "diary_min_relatedness": cfg.diary_min_relatedness,
            "chat_max_history_length": cfg.chat_max_history_length,
            "llm_temperature": cfg.llm_temperature,
            "llm_top_p": cfg.llm_top_p,
            "llm_top_k": cfg.llm_top_k,
            "llm_min_p": cfg.llm_min_p,
            "presence_penalty": cfg.llm_presence_penalty,
            "repetition_penalty": cfg.llm_repetition_penalty,
            "anti_repeat_trigger_max": cfg.anti_repeat_trigger_max,
            "anti_repeat_trigger_avg": cfg.anti_repeat_trigger_avg,
            "anti_repeat_max_history": cfg.anti_repeat_max_history,
            "suggest_ignore_chance": cfg.suggest_ignore_chance,
            "request_timeout_secs": cfg.request_timeout_secs,
            "video_max_frames": cfg.video_max_frames,
            "video_min_step_ms": cfg.video_min_step_ms,
            "remind_use_ask": cfg.remind_use_ask,
            "typing_simulation_min_wpm": cfg.typing_simulation_min_wpm,
            "typing_simulation_max_wpm": cfg.typing_simulation_max_wpm,
            "check_chats_on_startup": cfg.check_chats_on_startup,
            "chat_notification_filter": cfg.chat_notification_filter.value,
            "can_join_chats": cfg.can_join_chats,
            "can_leave_chats": cfg.can_leave_chats,
            "worker_count": cfg.worker_count,
        },
        "capabilities": {
            "web_search": {
                "enabled": cfg.capability_web_search,
                "ollama_bearer_key": cfg.web_search_ollama_key,
            },
            "vision": {
                "enabled": cfg.capability_vision,
                "llm_image_to_text": {
                    "model": cfg.llm_image_to_text.model,
                    "endpoint": {
                        "base_url": cfg.llm_image_to_text.endpoint.base_url,
                        "bearer_key": cfg.llm_image_to_text.endpoint.bearer_key,
                    }
                },
                "llm_image_to_text_cheap": {
                    "model": cfg.llm_image_to_text_cheap.model,
                    "endpoint": {
                        "base_url": cfg.llm_image_to_text_cheap.endpoint.base_url,
                        "bearer_key": cfg.llm_image_to_text_cheap.endpoint.bearer_key,
                    }
                }
            },
            "use_stickers": {
                "enabled": cfg.capability_use_stickers,
            },
            "take_photo": {
                "enabled": cfg.capability_take_photo,
                "sd": {
                    "endpoint": {
                        "base_url": cfg.sd_endpoint.base_url,
                        "bearer_key": cfg.sd_endpoint.bearer_key,
                    },
                    "checkpoint": cfg.sd_checkpoint,
                }
            },
            "hearing": {
                "enabled": cfg.capability_hearing,
                "llm_audio_to_text": {
                    "model": cfg.llm_audio_to_text.model,
                    "endpoint": {
                        "base_url": cfg.llm_audio_to_text.endpoint.base_url,
                        "bearer_key": cfg.llm_audio_to_text.endpoint.bearer_key,
                    }
                }
            },
            "record_voice": {
                "enabled": cfg.capability_record_voice,
                "backend": cfg.record_voice_backend.value,
                "elevenlabs": {
                    "key": cfg.record_voice_elevenlabs_key,
                    "voice_id": cfg.record_voice_elevenlabs_voice,
                },
                "openai": {
                    "url": cfg.record_voice_openai_url,
                    "key": cfg.record_voice_openai_key,
                    "model": cfg.record_voice_openai_model,
                    "voice": cfg.record_voice_openai_voice,
                    "response_format": cfg.record_voice_openai_format,
                    "pcm_sample_rate": cfg.record_voice_openai_pcm_sample_rate,
                }
            },
            "proxy": {
                "enabled": cfg.proxy_enabled,
            },
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def get_config() -> Config:
    """Get the global config instance."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def reload_config() -> Config:
    """Reload config from file."""
    global _CONFIG
    if _CONFIG_PATH is None:
        _CONFIG = load_config()
    else:
        _CONFIG = load_config(_CONFIG_PATH)
    return _CONFIG
