"""Tests for TZ-003: multimodal vision support in Telegram media."""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.openai_chat import Message, create_multimodal_content, normalize_image_bytes


def test_message_text_only_compatibility():
    """Text-only Message should serialize normally."""
    msg = Message(role="user", content="hello")
    d = msg.to_dict()
    assert d == {"role": "user", "content": "hello"}


def test_message_multimodal_content():
    """Multimodal Message with list content should serialize correctly."""
    content = [
        {"type": "text", "text": "look at this"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc123"},
        },
    ]
    msg = Message(role="user", content=content)
    d = msg.to_dict()
    assert d["role"] == "user"
    assert isinstance(d["content"], list)
    assert len(d["content"]) == 2
    assert d["content"][0]["type"] == "text"
    assert d["content"][1]["type"] == "image_url"


def test_create_multimodal_content_with_text_and_image():
    """create_multimodal_content should produce OpenAI-compatible format."""
    fake_image = b"fake-png-bytes"
    content = create_multimodal_content(
        text="describe this", image_data=fake_image, mime_type="image/png"
    )

    assert isinstance(content, list)
    assert len(content) == 2

    text_part = content[0]
    assert text_part["type"] == "text"
    assert text_part["text"] == "describe this"

    image_part = content[1]
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    b64_data = url.split(",", 1)[1]
    assert base64.b64decode(b64_data) == fake_image


def test_create_multimodal_content_text_only():
    """create_multimodal_content with empty image should return plain text."""
    content = create_multimodal_content(text="just text", image_data=b"", mime_type="image/png")
    assert isinstance(content, list)


def test_normalize_image_bytes_png_rgb():
    """PNG without alpha should be converted to JPEG."""
    # Create a PNG with RGB (no alpha)
    img = Image.new("RGB", (10, 10), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    result_bytes, mime = normalize_image_bytes(png_bytes, "image/png")
    assert mime == "image/jpeg"  # RGB images become JPEG

    # Verify it's valid JPEG
    result_img = Image.open(io.BytesIO(result_bytes))
    assert result_img.format == "JPEG"


def test_normalize_image_bytes_jpeg_normalized():
    """JPEG should be re-encoded with optimization."""
    img = Image.new("RGB", (10, 10), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=100)
    jpeg_bytes = buf.getvalue()

    result_bytes, mime = normalize_image_bytes(jpeg_bytes, "image/jpeg")
    assert mime == "image/jpeg"

    # Should still be valid JPEG
    result_img = Image.open(io.BytesIO(result_bytes))
    assert result_img.format == "JPEG"


def test_normalize_image_bytes_webp_to_png():
    """WebP should be converted to PNG."""
    # Create a WebP image
    img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    webp_bytes = buf.getvalue()

    result_bytes, mime = normalize_image_bytes(webp_bytes, "image/webp")
    assert mime == "image/png"
    assert result_bytes != webp_bytes

    # Verify it's valid PNG
    result_img = Image.open(io.BytesIO(result_bytes))
    assert result_img.format == "PNG"
    assert result_img.size == (10, 10)


def test_normalize_image_bytes_webp_no_alpha_to_jpeg():
    """WebP without alpha should convert to JPEG."""
    img = Image.new("RGB", (10, 10), color="green")
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    webp_bytes = buf.getvalue()

    result_bytes, mime = normalize_image_bytes(webp_bytes, "image/webp")
    assert mime == "image/jpeg"

    # Verify it's valid JPEG
    result_img = Image.open(io.BytesIO(result_bytes))
    assert result_img.format == "JPEG"


def test_normalize_image_bytes_invalid_raises():
    """Invalid image bytes should raise RuntimeError."""
    invalid_bytes = b"not an image"
    with pytest.raises(RuntimeError, match="Image normalization failed"):
        normalize_image_bytes(invalid_bytes, "image/png")


def test_message_with_tool_calls():
    """Message with tool_calls should serialize correctly."""
    msg = Message(
        role="assistant",
        content="calling tool",
        tool_calls=[{"id": "call_1", "function": {"name": "test", "arguments": "{}"}}],
    )
    d = msg.to_dict()
    assert d["role"] == "assistant"
    assert d["content"] == "calling tool"
    assert len(d["tool_calls"]) == 1


def test_message_tool_response():
    """Tool response Message should work with plain text."""
    msg = Message(role="tool", content="result data", tool_call_id="call_1")
    d = msg.to_dict()
    assert d["role"] == "tool"
    assert d["content"] == "result data"
    assert d["tool_call_id"] == "call_1"
