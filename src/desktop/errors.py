"""Desktop-specific exceptions (ТЗ-004)."""


class DesktopError(Exception):
    """Base exception for desktop subsystem."""


class DesktopDependencyError(DesktopError):
    """Raised when desktop dependencies (PySide6, Live2D, OpenGL) are missing."""


class DesktopRenderError(DesktopError):
    """Raised when rendering fails."""


class DesktopConfigError(DesktopError):
    """Raised when desktop configuration is invalid."""
