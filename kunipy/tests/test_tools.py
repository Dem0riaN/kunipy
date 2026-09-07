"""Tests for tools.py: anti-repeat detection and chat-membership tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfgmod  # noqa: E402
from src.config import Config  # noqa: E402
import logging

from src.tools import ToolContext, _check_anti_repeat, create_join_chat_tool, create_leave_chat_tool  # noqa: E402


def _use_config(**overrides) -> Config:
    cfg = Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    cfgmod._CONFIG = cfg
    return cfg


def test_anti_repeat_allows_first_message():
    _use_config()
    assert _check_anti_repeat("Hello there!", None) is None
    assert _check_anti_repeat("Hello there!", []) is None


def test_anti_repeat_blocks_near_identical_message():
    _use_config(anti_repeat_trigger_max=0.95, anti_repeat_trigger_avg=0.85, anti_repeat_max_history=32)
    recent = ["Hey, how's your day going so far?"]
    result = _check_anti_repeat("Hey, how's your day going so far?", recent)
    assert result is not None
    assert "too similar" in result


def test_anti_repeat_allows_distinct_message():
    _use_config(anti_repeat_trigger_max=0.95, anti_repeat_trigger_avg=0.85, anti_repeat_max_history=32)
    recent = ["Hey, how's your day going so far?"]
    result = _check_anti_repeat("Completely unrelated thought about pizza toppings.", recent)
    assert result is None


def test_anti_repeat_respects_history_window():
    # Only the last `anti_repeat_max_history` messages should be considered.
    _use_config(anti_repeat_trigger_max=0.95, anti_repeat_trigger_avg=0.85, anti_repeat_max_history=1)
    recent = ["This exact phrase repeats.", "Something totally different"]
    # The near-duplicate is outside the 1-message window, so it should pass.
    result = _check_anti_repeat("This exact phrase repeats.", recent)
    assert result is None


@pytest.mark.asyncio
async def test_join_chat_tool_success(monkeypatch):
    class FakeTelegram:
        async def join_chat_by_link(self, link):
            assert link == "https://t.me/+abc123"
            return 999

    tool = create_join_chat_tool(FakeTelegram())
    ctx = ToolContext(args={"invite_link": "https://t.me/+abc123"}, logger=logging.getLogger("test"), temporary_context=[])
    result = await tool.handler(ctx)
    assert "999" in result


@pytest.mark.asyncio
async def test_join_chat_tool_failure():
    class FakeTelegram:
        async def join_chat_by_link(self, link):
            raise RuntimeError("invite link expired")

    tool = create_join_chat_tool(FakeTelegram())
    ctx = ToolContext(args={"invite_link": "https://t.me/+dead"}, logger=logging.getLogger("test"), temporary_context=[])
    result = await tool.handler(ctx)
    assert "Error" in result


@pytest.mark.asyncio
async def test_leave_chat_tool():
    calls = []

    class FakeTelegram:
        async def leave_chat(self, chat_id):
            calls.append(chat_id)

    tool = create_leave_chat_tool(FakeTelegram())
    ctx = ToolContext(args={"chat_id": 555}, logger=logging.getLogger("test"), temporary_context=[])
    result = await tool.handler(ctx)
    assert calls == [555]
    assert "555" in result
