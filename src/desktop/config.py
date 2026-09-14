"""Desktop configuration (ТЗ-004).

Adapter pattern: converts Config → DesktopConfig so desktop package
does not depend on full Config class.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config


@dataclass(frozen=True)
class DesktopConfig:
    """Desktop character configuration."""

    enabled: bool = False
    window_width: int = 800
    window_height: int = 600
    fps: int = 30
    model_path: str = ""
    motion_dir: str = ""

    @classmethod
    def from_app_config(cls, config: "Config") -> "DesktopConfig":
        """Extract desktop settings from application Config."""
        return cls(
            enabled=config.desktop_enabled,
            window_width=config.desktop_window_width,
            window_height=config.desktop_window_height,
            fps=config.desktop_fps,
            model_path=config.desktop_model_path,
            motion_dir=config.desktop_motion_dir,
        )
