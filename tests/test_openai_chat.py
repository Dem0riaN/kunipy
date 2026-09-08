"""Tests for openai_chat.py: describe_image / synthesize_speech against a mock upstream."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfgmod  # noqa: E402
from src.config import Config, Endpoint, EndpointAndModel, TTSBackend  # noqa: E402
from src.openai_chat import ChatResponse, OpenAIChat  # noqa: E402


@pytest.fixture
async def mock_vision_server():
    seen = {}

    async def chat_completions(request: web.Request) -> web.Response:
        body = await request.json()
        seen["body"] = body
        return web.json_response({
            "id": "cmpl-vision",
            "model": "vision-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "A cat sitting on a windowsill."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        })

    app = web.Application()
    app.router.add_post("/v1/chat/completions", chat_completions)
    server = TestServer(app)
    await server.start_server()
    try:
        yield server, seen
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_describe_image_sends_base64_and_returns_text(mock_vision_server):
    server, seen = mock_vision_server
    cfg = Config()
    cfg.llm_image_to_text = EndpointAndModel(
        endpoint=Endpoint(base_url=f"http://{server.host}:{server.port}/v1", bearer_key="k"),
        model="vision-model",
    )
    cfgmod._CONFIG = cfg

    client = OpenAIChat(endpoint=cfg.llm)
    try:
        result = await client.describe_image(b"fake-image-bytes", mime_type="image/png")
    finally:
        await client.close()

    assert result == "A cat sitting on a windowsill."
    sent_content = seen["body"]["messages"][0]["content"]
    image_part = next(p for p in sent_content if p["type"] == "image_url")
    b64_payload = image_part["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(b64_payload) == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_describe_image_returns_empty_when_unconfigured():
    cfg = Config()
    cfg.llm_image_to_text = EndpointAndModel(endpoint=Endpoint(base_url="", bearer_key=""), model="")
    cfgmod._CONFIG = cfg

    client = OpenAIChat(endpoint=cfg.llm)
    try:
        result = await client.describe_image(b"bytes")
    finally:
        await client.close()

    assert result == ""


@pytest.fixture
async def mock_tts_server():
    async def speech(request: web.Request) -> web.Response:
        return web.Response(body=b"FAKE_AUDIO_BYTES", content_type="audio/mpeg")

    app = web.Application()
    app.router.add_post("/v1/audio/speech", speech)
    server = TestServer(app)
    await server.start_server()
    try:
        yield server
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_synthesize_speech_openai_backend(mock_tts_server):
    server = mock_tts_server
    cfg = Config()
    cfg.capability_record_voice = True
    cfg.record_voice_backend = TTSBackend.OPENAI
    cfg.record_voice_openai_url = f"http://{server.host}:{server.port}/v1"
    cfg.record_voice_openai_key = "k"
    cfgmod._CONFIG = cfg

    client = OpenAIChat(endpoint=cfg.llm)
    try:
        audio = await client.synthesize_speech("hello there")
    finally:
        await client.close()

    assert audio == b"FAKE_AUDIO_BYTES"


@pytest.mark.asyncio
async def test_synthesize_speech_disabled_returns_none():
    cfg = Config()
    cfg.capability_record_voice = False
    cfgmod._CONFIG = cfg

    client = OpenAIChat(endpoint=cfg.llm)
    try:
        audio = await client.synthesize_speech("hello")
    finally:
        await client.close()

    assert audio is None


def test_record_usage_metrics_handles_null_prompt_tokens_details():
    """Regression test: some servers send "prompt_tokens_details": null
    explicitly rather than omitting the key, which used to crash with
    AttributeError: 'NoneType' object has no attribute 'get'."""
    client = OpenAIChat(endpoint=Config().llm)
    response = ChatResponse(
        id="x", model="m", choices=[],
        usage={"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": None},
    )
    client._record_usage_metrics(response)  # must not raise


def test_record_usage_metrics_handles_missing_usage():
    client = OpenAIChat(endpoint=Config().llm)
    response = ChatResponse(id="x", model="m", choices=[], usage=None)
    client._record_usage_metrics(response)  # must not raise


def test_record_usage_metrics_handles_non_dict_usage():
    client = OpenAIChat(endpoint=Config().llm)
    response = ChatResponse(id="x", model="m", choices=[], usage="not a dict")
    client._record_usage_metrics(response)  # must not raise
