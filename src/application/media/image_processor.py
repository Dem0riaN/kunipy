"""Image processing for LLM multimodal content.

Handles image normalization and encoding for OpenAI-compatible vision APIs.
Extracted from openai_chat.py to maintain proper layer separation.
"""

import base64
import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image normalization and encoding for LLM APIs."""

    @staticmethod
    def normalize_image_bytes(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
        """Normalize image bytes to PNG or JPEG format.

        Handles WebP decoding and ensures the image is in a format compatible
        with OpenAI vision models. Conversion happens entirely in memory.

        Args:
            image_data: Raw image bytes (any format Pillow supports)
            mime_type: Original MIME type (e.g., "image/webp", "image/jpeg")

        Returns:
            Tuple of (normalized_bytes, normalized_mime_type)
            - For images with transparency: PNG
            - For images without transparency: JPEG (smaller size)

        Raises:
            RuntimeError: If image cannot be decoded
        """
        try:
            # Decode image
            img = Image.open(BytesIO(image_data))

            # Determine output format based on transparency
            has_alpha = img.mode in ("RGBA", "LA", "P") and (
                img.mode == "P" and "transparency" in img.info or img.mode in ("RGBA", "LA")
            )

            output = BytesIO()
            if has_alpha:
                # Preserve transparency with PNG
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                img.save(output, format="PNG", optimize=True)
                return output.getvalue(), "image/png"
            else:
                # Convert to JPEG for better compression
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue(), "image/jpeg"
        except Exception as e:
            logger.error(f"Failed to normalize image: {e}")
            raise RuntimeError(f"Image normalization failed: {e}") from e

    @staticmethod
    def create_multimodal_content(text: str, image_data: bytes, mime_type: str) -> list[dict]:
        """Create OpenAI-compatible multimodal content with text and image.

        Args:
            text: Text content (can be empty)
            image_data: Image bytes
            mime_type: Image MIME type

        Returns:
            List of content parts in OpenAI format:
            [
                {"type": "text", "text": "..."},
                {"type": "image_url", "image_url": {"url": "data:..."}}
            ]
        """
        # Normalize image format if needed
        if mime_type == "image/webp" or mime_type not in ("image/jpeg", "image/png"):
            image_data, mime_type = ImageProcessor.normalize_image_bytes(image_data, mime_type)

        b64 = base64.b64encode(image_data).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"

        content_parts = []
        if text:
            content_parts.append({"type": "text", "text": text})
        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})

        return content_parts
