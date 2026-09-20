"""Image generation for kunipy.

Wraps Stable Diffusion API (or other) to generate images.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import aiohttp

from .config import get_config

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images using Stable Diffusion (or mock)."""

    def __init__(self, endpoint: str | None = None, checkpoint: str | None = None):
        config = get_config()
        self.enabled = config.capability_take_photo
        self.endpoint = endpoint or config.sd_endpoint.base_url or "http://localhost:7860/"
        self.checkpoint = checkpoint or config.sd_checkpoint
        self._bearer_key = config.sd_endpoint.bearer_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._bearer_key:
                headers["Authorization"] = f"Bearer {self._bearer_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int | None = None,
    ) -> bytes | None:
        """Generate an image from a prompt.

        Returns the image data as bytes (PNG/JPEG) or None on failure.
        """
        if not self.enabled:
            logger.warning("Image generation disabled")
            return None

        # If endpoint is not available, return mock
        if not self.endpoint:
            logger.warning("No SD endpoint configured, returning mock image")
            return self._mock_image(prompt)

        try:
            session = await self._get_session()
            # Use txt2img API (SD WebUI)
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed,
                "checkpoint": self.checkpoint,
            }
            # Add trailing slash if needed
            url = self.endpoint.rstrip("/") + "/sdapi/v1/txt2img"
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"SD API error: {resp.status}")
                    return None
                data = await resp.json()
                # data['images'] is list of base64-encoded images
                if not data.get("images"):
                    return None
                image_data = base64.b64decode(data["images"][0])
                return image_data
        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error(f"Image generation failed: {e}")
            return None

    async def generate_and_save(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int | None = None,
        output_dir: str = "data/generated_images",
    ) -> str | None:
        """Generate an image and save it to disk. Returns the local file path, or None on failure."""
        data = await self.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
        )
        if not data:
            return None

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        import re
        import time
        safe_prompt = re.sub(r"[^a-zA-Z0-9_-]+", "_", prompt[:40]).strip("_") or "image"
        filename = f"{int(time.time() * 1000)}_{safe_prompt}.png"
        path = out_dir / filename
        path.write_bytes(data)
        return str(path)

    def _mock_image(self, prompt: str) -> bytes:
        """Return a mock image (a small placeholder)."""
        # Simple red dot on white (simulated)
        # For now, return a tiny PNG placeholder
        # In reality, we would generate a dummy image.
        # We'll return a 1x1 transparent pixel as placeholder.
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton instance
_generator: ImageGenerator | None = None


def get_image_generator() -> ImageGenerator:
    """Get global image generator instance."""
    global _generator
    if _generator is None:
        _generator = ImageGenerator()
    return _generator
