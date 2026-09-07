"""Tests for proxy_server.py against a local mock upstream (no real network)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfgmod  # noqa: E402
from src.config import Config, Endpoint, EndpointAndModel  # noqa: E402
from src.proxy_server import create_proxy_app  # noqa: E402


@pytest.fixture
async def mock_upstream():
    """A tiny aiohttp server standing in for a real OpenAI-compatible endpoint."""
    calls = {"chat_completions": []}

    async def chat_completions(request: web.Request) -> web.Response:
        body = await request.json()
        calls["chat_completions"].append(body)
        return web.json_response({
            "id": "cmpl-mock",
            "model": "mock-model",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from mock upstream!"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    async def models(request: web.Request) -> web.Response:
        return web.json_response({"object": "list", "data": [{"id": "mock-model"}]})

    app = web.Application()
    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_get("/v1/models", models)
    server = TestServer(app)
    await server.start_server()
    try:
        yield server, calls
    finally:
        await server.close()


def _configure_proxy_upstream(server: TestServer) -> None:
    cfg = Config()
    base_url = f"http://{server.host}:{server.port}/v1"
    cfg.proxy_upstream = EndpointAndModel(endpoint=Endpoint(base_url=base_url, bearer_key=""), model="mock-model")
    cfgmod._CONFIG = cfg


@pytest.mark.asyncio
async def test_chat_completions_injects_system_prompt_and_returns_answer(mock_upstream, tmp_path, monkeypatch):
    server, calls = mock_upstream
    _configure_proxy_upstream(server)
    monkeypatch.chdir(tmp_path)  # so character_base.md gets created in a scratch dir

    app = create_proxy_app(diary=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proxy.local") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "whatever", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Hello from mock upstream!"

    # The upstream should have received our injected system prompt, not just "hi".
    assert len(calls["chat_completions"]) == 1
    sent_messages = calls["chat_completions"][0]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "Kuni" in sent_messages[0]["content"]


@pytest.mark.asyncio
async def test_chat_completions_streaming_returns_sse(mock_upstream, tmp_path, monkeypatch):
    server, _calls = mock_upstream
    _configure_proxy_upstream(server)
    monkeypatch.chdir(tmp_path)

    app = create_proxy_app(diary=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proxy.local") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "Hello from mock upstream!" in body
    assert body.strip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_other_v1_routes_are_passed_through(mock_upstream, tmp_path, monkeypatch):
    server, _calls = mock_upstream
    _configure_proxy_upstream(server)
    monkeypatch.chdir(tmp_path)

    app = create_proxy_app(diary=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proxy.local") as client:
        resp = await client.get("/v1/models")

    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": [{"id": "mock-model"}]}
