"""Configuration management for kunipy.

Reads and parses config.toml, supports hot-reloading, provides typed access.
REFACTORED: No singleton pattern - use load_config() to get Config instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

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
    """LLM endpoint configuration."""
    base_url: str = "https://api.openai.com/v1"
    bearer_key: str = ""


@dataclass
class EndpointAndModel:
    """Endpoint + model pair."""
    endpoint: Endpoint = field(default_factory=Endpoint)
    model: str = ""


@dataclass
class Config:
    """Application configuration."""

    # Core LLM
    llm: EndpointAndModel = field(default_factory=EndpointAndModel)

    # Embedding model (for memory system and diary)
    embedding: EndpointAndModel = field(default_factory=EndpointAndModel)

    # Character
    character_name: str = "Куни"
    character_nickname: str = ""

    # Owner (papik)
    papik_name: str = ""
    papik_chat_id: int = 0

    # Telegram
    telegram_enabled: bool = False
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_database_directory: str = "telegram_data"

    # Diary
    diary_enabled: bool = False
    diary_dir: str = "diary"
    diary_min_relatedness: float = 0.5
    diary_plagiarism_threshold: float = 0.95
    remind_use_ask: bool = True

    # Lockdown
    lockdown: LockdownMode = LockdownMode.NONE

    # Capabilities
    capability_hearing: bool = False
    capability_vision: bool = False
    capability_take_photo: bool = False
    capability_record_voice: bool = False
    capability_use_stickers: bool = False
    capability_web_search: bool = False
    capability_generate_images: bool = False
    can_join_chats: bool = False
    can_leave_chats: bool = False

    # Image generation
    image_generator: EndpointAndModel = field(default_factory=EndpointAndModel)
    sd_endpoint: EndpointAndModel = field(default_factory=EndpointAndModel)
    sd_checkpoint: str = ""

    # Hearing (transcription)
    hearing: EndpointAndModel = field(default_factory=EndpointAndModel)

    # Vision
    vision: EndpointAndModel = field(default_factory=EndpointAndModel)
    llm_image_to_text: EndpointAndModel = field(default_factory=EndpointAndModel)
    llm_image_to_text_cheap: EndpointAndModel = field(default_factory=EndpointAndModel)

    # Audio transcription
    llm_audio_to_text: EndpointAndModel = field(default_factory=EndpointAndModel)

    # TTS (record_voice)
    record_voice_backend: TTSBackend = TTSBackend.ELEVENLABS
    record_voice_elevenlabs_key: str = ""
    record_voice_elevenlabs_voice_id: str = ""
    record_voice_elevenlabs_voice: str = ""
    record_voice_elevenlabs_model_id: str = "eleven_turbo_v2_5"
    record_voice_openai_key: str = ""
    record_voice_openai_url: str = "https://api.openai.com/v1"
    record_voice_openai_model: str = "tts-1"
    record_voice_openai_voice: str = "nova"
    record_voice_openai_format: str = "opus"
    record_voice_openai_pcm_sample_rate: int = 24000

    # Proxy server
    proxy_enabled: bool = False
    proxy_port: int = 8080
    proxy_upstream: EndpointAndModel = field(default_factory=EndpointAndModel)

    # Worker
    worker_sleep_enabled: bool = False
    worker_sleep_timeout: int = 300
    worker_count: int = 1

    # LLM parameters
    request_timeout_secs: int = 120
    llm_temperature: float = 1.0
    llm_top_p: float = 1.0
    llm_top_k: int = 0
    llm_min_p: float = 0.0
    llm_presence_penalty: float = 0.0
    llm_repetition_penalty: float = 1.0

    # Anti-repeat system
    anti_repeat_max_history: int = 5
    anti_repeat_trigger_max: float = 0.85
    anti_repeat_trigger_avg: float = 0.70

    # Typing simulation
    typing_simulation_min_wpm: int = 40
    typing_simulation_max_wpm: int = 80

    # Web search
    web_search_ollama_key: str = ""

    # Document processing
    document_processing_enabled: bool = True
    document_max_size_bytes: int = 1024 * 1024  # 1MB physical file limit
    document_max_context_chars: int = 50000      # ~12.5k tokens for LLM context

    # Startup behavior
    check_chats_on_startup: bool = True

    # Notification filtering
    chat_notification_filter: LockdownMode = LockdownMode.NONE
    suggest_ignore_chance: float = 0.0

    # Metrics
    metrics_enabled: bool = False
    metrics_port: int = 9090

    # Application timezone
    timezone: str = "UTC"
    _timezone_info: ZoneInfo | None = field(default=None, init=False, repr=False)

    @property
    def timezone_info(self) -> ZoneInfo:
        """Get validated ZoneInfo instance for application timezone.

        Lazily validates and caches the timezone on first access.

        Returns:
            ZoneInfo instance for the configured timezone

        Raises:
            ValueError: If timezone string is invalid
        """
        if self._timezone_info is None:
            try:
                self._timezone_info = ZoneInfo(self.timezone)
            except Exception as e:
                raise ValueError(
                    f"Invalid timezone '{self.timezone}'. Must be a valid IANA timezone "
                    f"(e.g., 'UTC', 'Europe/Amsterdam', 'America/New_York'). Error: {e}"
                ) from e
        return self._timezone_info

    @staticmethod
    def from_toml(path: Path | str) -> Config:
        """Load configuration from TOML file.

        Args:
            path: Path to config.toml

        Returns:
            Parsed Config instance
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "rb") as f:
            data = tomli.load(f)

        cfg = Config()

        # Core LLM
        llm_cfg = data.get("llm", {})
        llm_endpoint = llm_cfg.get("endpoint", {})
        cfg.llm.endpoint.base_url = llm_endpoint.get("base_url", cfg.llm.endpoint.base_url)
        cfg.llm.endpoint.bearer_key = llm_endpoint.get("bearer_key", cfg.llm.endpoint.bearer_key)
        cfg.llm.model = llm_cfg.get("model", cfg.llm.model)

        # Character
        character = data.get("character", {})
        cfg.character_name = character.get("name", cfg.character_name)
        # Owner (papik) - read from [character] section
        cfg.papik_chat_id = character.get("papik_chat_id", cfg.papik_chat_id)

        # Telegram
        telegram = data.get("telegram", {})
        cfg.telegram_enabled = telegram.get("enabled", cfg.telegram_enabled)
        cfg.telegram_api_id = telegram.get("api_id", cfg.telegram_api_id)
        cfg.telegram_api_hash = telegram.get("api_hash", cfg.telegram_api_hash)
        cfg.telegram_phone = telegram.get("phone", cfg.telegram_phone)
        cfg.telegram_database_directory = telegram.get("database_directory", cfg.telegram_database_directory)

        # Diary
        diary_cfg = data.get("diary", {})
        cfg.diary_enabled = diary_cfg.get("enabled", cfg.diary_enabled)
        cfg.diary_dir = diary_cfg.get("directory", cfg.diary_dir)
        cfg.diary_min_relatedness = diary_cfg.get("min_relatedness", cfg.diary_min_relatedness)
        cfg.diary_plagiarism_threshold = diary_cfg.get("plagiarism_threshold", cfg.diary_plagiarism_threshold)

        # Lockdown
        lockdown_cfg = data.get("lockdown", {})
        mode_str = lockdown_cfg.get("mode", "none")
        cfg.lockdown = LockdownMode(mode_str) if mode_str else LockdownMode.NONE
        # papik_chat_id already loaded from top-level earlier

        # Capabilities
        capabilities = data.get("capabilities", {})

        # Hearing
        hearing_cfg = capabilities.get("hearing", {})
        cfg.capability_hearing = hearing_cfg.get("enabled", cfg.capability_hearing)
        hearing_endpoint = hearing_cfg.get("endpoint", {})
        cfg.hearing.endpoint.base_url = hearing_endpoint.get("base_url", cfg.hearing.endpoint.base_url)
        cfg.hearing.endpoint.bearer_key = hearing_endpoint.get("bearer_key", cfg.hearing.endpoint.bearer_key)
        cfg.hearing.model = hearing_cfg.get("model", cfg.hearing.model)

        # Vision
        vision_cfg = capabilities.get("vision", {})
        cfg.capability_vision = vision_cfg.get("enabled", cfg.capability_vision)
        vision_endpoint = vision_cfg.get("endpoint", {})
        cfg.vision.endpoint.base_url = vision_endpoint.get("base_url", cfg.vision.endpoint.base_url)
        cfg.vision.endpoint.bearer_key = vision_endpoint.get("bearer_key", cfg.vision.endpoint.bearer_key)
        cfg.vision.model = vision_cfg.get("model", cfg.vision.model)

        # Image generation
        image_gen_cfg = capabilities.get("generate_images", {})
        cfg.capability_generate_images = image_gen_cfg.get("enabled", cfg.capability_generate_images)
        image_endpoint = image_gen_cfg.get("endpoint", {})
        cfg.image_generator.endpoint.base_url = image_endpoint.get("base_url", cfg.image_generator.endpoint.base_url)
        cfg.image_generator.endpoint.bearer_key = image_endpoint.get("bearer_key", cfg.image_generator.endpoint.bearer_key)
        cfg.image_generator.model = image_gen_cfg.get("model", cfg.image_generator.model)

        # Simple boolean capabilities
        cfg.capability_take_photo = capabilities.get("take_photo", {}).get("enabled", cfg.capability_take_photo)
        cfg.capability_use_stickers = capabilities.get("use_stickers", {}).get("enabled", cfg.capability_use_stickers)
        cfg.capability_web_search = capabilities.get("web_search", {}).get("enabled", cfg.capability_web_search)
        cfg.can_join_chats = capabilities.get("join_chats", {}).get("enabled", cfg.can_join_chats)
        cfg.can_leave_chats = capabilities.get("leave_chats", {}).get("enabled", cfg.can_leave_chats)

        # TTS (record_voice)
        record_voice_cfg = capabilities.get("record_voice", {})
        cfg.capability_record_voice = record_voice_cfg.get("enabled", cfg.capability_record_voice)
        backend_str = record_voice_cfg.get("backend", "elevenlabs")
        cfg.record_voice_backend = TTSBackend(backend_str) if backend_str else TTSBackend.ELEVENLABS

        elevenlabs_tts = record_voice_cfg.get("elevenlabs", {})
        cfg.record_voice_elevenlabs_key = elevenlabs_tts.get("key", cfg.record_voice_elevenlabs_key)
        cfg.record_voice_elevenlabs_voice_id = elevenlabs_tts.get("voice_id", cfg.record_voice_elevenlabs_voice_id)
        cfg.record_voice_elevenlabs_model_id = elevenlabs_tts.get("model_id", cfg.record_voice_elevenlabs_model_id)

        openai_tts = record_voice_cfg.get("openai", {})
        cfg.record_voice_openai_key = openai_tts.get("key", cfg.record_voice_openai_key)
        cfg.record_voice_openai_model = openai_tts.get("model", cfg.record_voice_openai_model)
        cfg.record_voice_openai_voice = openai_tts.get("voice", cfg.record_voice_openai_voice)
        cfg.record_voice_openai_format = openai_tts.get("response_format", cfg.record_voice_openai_format)
        cfg.record_voice_openai_pcm_sample_rate = openai_tts.get("pcm_sample_rate", cfg.record_voice_openai_pcm_sample_rate)

        # Proxy (top-level section, not in capabilities)
        proxy_cfg = data.get("proxy", {})
        cfg.proxy_enabled = proxy_cfg.get("enabled", cfg.proxy_enabled)
        cfg.proxy_port = proxy_cfg.get("port", cfg.proxy_port)
        upstream = proxy_cfg.get("upstream", {})
        cfg.proxy_upstream.model = upstream.get("model", cfg.proxy_upstream.model)
        if "endpoint" in upstream:
            cfg.proxy_upstream.endpoint.base_url = upstream["endpoint"].get("base_url", cfg.proxy_upstream.endpoint.base_url)
            cfg.proxy_upstream.endpoint.bearer_key = upstream["endpoint"].get("bearer_key", cfg.proxy_upstream.endpoint.bearer_key)

        # Worker
        worker_cfg = data.get("worker", {})
        cfg.worker_sleep_enabled = worker_cfg.get("sleep_enabled", cfg.worker_sleep_enabled)
        cfg.worker_sleep_timeout = worker_cfg.get("sleep_timeout", cfg.worker_sleep_timeout)

        # Application timezone
        app_cfg = data.get("app", {})
        cfg.timezone = app_cfg.get("timezone", cfg.timezone)

        # Validate timezone immediately on load
        _ = cfg.timezone_info

        return cfg


def load_config(config_path: str | Path = "config.toml") -> Config:
    """Load config from TOML file.

    No singleton pattern - returns fresh Config instance.
    Each caller owns their Config instance.

    Args:
        config_path: Path to config.toml file

    Returns:
        Config instance parsed from file

    Raises:
        FileNotFoundError: If config file doesn't exist
        tomli.TOMLDecodeError: If config file is malformed
    """
    return Config.from_toml(config_path)


def save_config(cfg: Config, path: Path | str = "config.toml") -> None:
    """Save config to TOML file.

    Args:
        cfg: Config instance to save
        path: Output path
    """
    path = Path(path)

    data = {
        "app": {
            "timezone": cfg.timezone,
        },
        "llm": {
            "model": cfg.llm.model,
            "endpoint": {
                "base_url": cfg.llm.endpoint.base_url,
                "bearer_key": cfg.llm.endpoint.bearer_key,
            },
        },
        "character": {
            "name": cfg.character_name,
        },
        "telegram": {
            "enabled": cfg.telegram_enabled,
            "api_id": cfg.telegram_api_id,
            "api_hash": cfg.telegram_api_hash,
            "phone": cfg.telegram_phone,
            "database_directory": cfg.telegram_database_directory,
        },
        "diary": {
            "enabled": cfg.diary_enabled,
            "directory": cfg.diary_dir,
            "min_relatedness": cfg.diary_min_relatedness,
            "plagiarism_threshold": cfg.diary_plagiarism_threshold,
        },
        "lockdown": {
            "mode": cfg.lockdown.value,
            "papik_chat_id": cfg.papik_chat_id,
        },
        "worker": {
            "sleep_enabled": cfg.worker_sleep_enabled,
            "sleep_timeout": cfg.worker_sleep_timeout,
        },
        "capabilities": {
            "hearing": {
                "enabled": cfg.capability_hearing,
                "model": cfg.hearing.model,
                "endpoint": {
                    "base_url": cfg.hearing.endpoint.base_url,
                    "bearer_key": cfg.hearing.endpoint.bearer_key,
                },
            },
            "vision": {
                "enabled": cfg.capability_vision,
                "model": cfg.vision.model,
                "endpoint": {
                    "base_url": cfg.vision.endpoint.base_url,
                    "bearer_key": cfg.vision.endpoint.bearer_key,
                },
            },
            "generate_images": {
                "enabled": cfg.capability_generate_images,
                "model": cfg.image_generator.model,
                "endpoint": {
                    "base_url": cfg.image_generator.endpoint.base_url,
                    "bearer_key": cfg.image_generator.endpoint.bearer_key,
                },
            },
            "take_photo": {
                "enabled": cfg.capability_take_photo,
            },
            "record_voice": {
                "enabled": cfg.capability_record_voice,
                "backend": cfg.record_voice_backend.value,
                "elevenlabs": {
                    "key": cfg.record_voice_elevenlabs_key,
                    "voice_id": cfg.record_voice_elevenlabs_voice_id,
                    "model_id": cfg.record_voice_elevenlabs_model_id,
                },
                "openai": {
                    "key": cfg.record_voice_openai_key,
                    "model": cfg.record_voice_openai_model,
                    "voice": cfg.record_voice_openai_voice,
                    "response_format": cfg.record_voice_openai_format,
                    "pcm_sample_rate": cfg.record_voice_openai_pcm_sample_rate,
                },
            },
            "use_stickers": {
                "enabled": cfg.capability_use_stickers,
            },
            "web_search": {
                "enabled": cfg.capability_web_search,
            },
            "join_chats": {
                "enabled": cfg.can_join_chats,
            },
            "leave_chats": {
                "enabled": cfg.can_leave_chats,
            },
            "proxy": {
                "enabled": cfg.proxy_enabled,
                "port": cfg.proxy_port,
                "upstream": {
                    "model": cfg.proxy_upstream.model,
                    "endpoint": {
                        "base_url": cfg.proxy_upstream.endpoint.base_url,
                        "bearer_key": cfg.proxy_upstream.endpoint.bearer_key,
                    },
                },
            },
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


# Singleton pattern removed - use load_config() instead
# Legacy modules that use get_config() need refactoring
def get_config() -> Config:
    """DEPRECATED: Singleton pattern removed.

    This function exists only for backward compatibility with legacy modules
    (openai_chat.py, telegram_client.py, tools.py, etc.) that haven't been
    fully refactored yet.

    DO NOT USE in new code - use dependency injection instead:
        config = load_config()
        component = Component(config=config)
    """
    # Lazy load singleton for legacy compatibility
    global _LEGACY_CONFIG
    if _LEGACY_CONFIG is None:
        _LEGACY_CONFIG = load_config()
    return _LEGACY_CONFIG


# Legacy singleton state
_LEGACY_CONFIG: Config | None = None
