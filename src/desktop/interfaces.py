"""Desktop interfaces (ТЗ-004).

13 Protocol interfaces following SRP principle. No god objects.
These define contracts for desktop subsystems (Live2D, window management,
rendering, motion, expressions, etc).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ICharacterRenderer(Protocol):
    """Renders the character model."""

    async def render(self) -> None:
        """Render current frame."""
        ...

    async def update(self, delta_time: float) -> None:
        """Update character state for next frame."""
        ...


@runtime_checkable
class IMotionController(Protocol):
    """Controls character motion/animation."""

    async def play_motion(self, motion_name: str) -> None:
        """Play a specific motion."""
        ...

    async def stop_motion(self) -> None:
        """Stop current motion."""
        ...

    async def is_playing(self) -> bool:
        """Check if motion is currently playing."""
        ...


@runtime_checkable
class IEnvironmentRenderer(Protocol):
    """Renders environment/background."""

    async def render(self) -> None:
        """Render environment."""
        ...

    async def load_scene(self, scene_name: str) -> None:
        """Load a specific scene."""
        ...


@runtime_checkable
class IModelLoader(Protocol):
    """Loads Live2D model."""

    async def load(self, model_path: str) -> bool:
        """Load model from path. Returns True on success."""
        ...

    async def unload(self) -> None:
        """Unload current model."""
        ...

    async def is_loaded(self) -> bool:
        """Check if model is loaded."""
        ...


@runtime_checkable
class IMotionLoader(Protocol):
    """Loads motion files."""

    async def load(self, motion_path: str) -> bool:
        """Load motion from path. Returns True on success."""
        ...

    async def unload(self) -> None:
        """Unload all motions."""
        ...

    async def list_motions(self) -> list[str]:
        """List available motion names."""
        ...


@runtime_checkable
class IWindowManager(Protocol):
    """Manages desktop window."""

    async def create_window(self, width: int, height: int) -> None:
        """Create window with given dimensions."""
        ...

    async def destroy_window(self) -> None:
        """Destroy window."""
        ...

    async def is_open(self) -> bool:
        """Check if window is open."""
        ...


@runtime_checkable
class IConfig(Protocol):
    """Desktop configuration interface."""

    @property
    def enabled(self) -> bool:
        """Is desktop enabled?"""
        ...

    @property
    def window_width(self) -> int:
        """Window width."""
        ...

    @property
    def window_height(self) -> int:
        """Window height."""
        ...

    @property
    def fps(self) -> int:
        """Target FPS."""
        ...


@runtime_checkable
class ILipSyncProvider(Protocol):
    """Provides lip sync data."""

    async def get_lip_data(self, text: str) -> list[float]:
        """Get lip sync values for text. Returns list of mouth open values (0-1)."""
        ...

    async def update(self, delta_time: float) -> None:
        """Update lip sync state."""
        ...


@runtime_checkable
class IExpressionController(Protocol):
    """Controls facial expressions."""

    async def set_expression(self, expression_name: str, weight: float) -> None:
        """Set expression with weight (0-1)."""
        ...

    async def reset_expressions(self) -> None:
        """Reset to neutral expression."""
        ...


@runtime_checkable
class IEyeContactController(Protocol):
    """Controls eye gaze/contact."""

    async def look_at(self, x: float, y: float) -> None:
        """Look at screen coordinates."""
        ...

    async def reset_gaze(self) -> None:
        """Reset to default gaze."""
        ...


@runtime_checkable
class IIdleAnimationController(Protocol):
    """Controls idle animations."""

    async def start(self) -> None:
        """Start idle animations."""
        ...

    async def stop(self) -> None:
        """Stop idle animations."""
        ...

    async def update(self, delta_time: float) -> None:
        """Update idle animation state."""
        ...


@runtime_checkable
class ISceneDirector(Protocol):
    """Directs scene composition."""

    async def compose_scene(self) -> None:
        """Compose current scene (character + environment)."""
        ...

    async def transition_to(self, scene_name: str) -> None:
        """Transition to a new scene."""
        ...


@runtime_checkable
class ICharacterState(Protocol):
    """Character state interface."""

    @property
    def is_speaking(self) -> bool:
        """Is character currently speaking?"""
        ...

    @property
    def current_expression(self) -> str:
        """Current expression name."""
        ...

    @property
    def current_motion(self) -> str:
        """Current motion name."""
        ...
