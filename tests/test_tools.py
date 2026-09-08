"""Tests for tools.py: anti-repeat detection and chat-membership tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.config as cfgmod  # noqa: E402
from src.config import Config  # noqa: E402
import logging

from src.telegram_client import TelegramChat  # noqa: E402
from src.tools import (  # noqa: E402
    ToolContext,
    _check_anti_repeat,
    create_join_chat_tool,
    create_leave_chat_tool,
    create_send_telegram_message_tool,
)


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


@pytest.mark.asyncio
async def test_send_telegram_message_rejects_mismatched_chat_id():
    """Regression test mirroring the original C++ kuni's cross-chat guard:
    the model must not be able to send to a chat_id other than the one
    this tool instance is bound to."""
    class FakeTelegram:
        async def get_chat_history(self, chat_id, limit=30):
            return []

    chat = TelegramChat(id=111, title="Alice", type="private")
    tool = create_send_telegram_message_tool(FakeTelegram(), chat, recent_bot_messages=[])
    ctx = ToolContext(
        args={"text": "hi", "chat_id": 999},
        logger=logging.getLogger("test"),
        temporary_context=[],
    )
    result = await tool.handler(ctx)
    assert "Error" in result
    assert "other chats" in result


@pytest.mark.asyncio
async def test_send_telegram_message_rejects_reply_to_outside_history():
    class FakeTelegram:
        async def get_chat_history(self, chat_id, limit=30):
            return []  # empty history -- the requested reply target isn't here

        async def send_message(self, chat_id, text, reply_to_message_id=None):
            raise AssertionError("send_message should not be called")

        async def send_typing(self, chat_id):
            pass

    chat = TelegramChat(id=111, title="Alice", type="private")
    tool = create_send_telegram_message_tool(FakeTelegram(), chat, recent_bot_messages=[])
    ctx = ToolContext(
        args={"text": "hi", "reply_to": 555},
        logger=logging.getLogger("test"),
        temporary_context=[],
    )
    result = await tool.handler(ctx)
    assert "Error" in result
    assert "isn't in this chat" in result


@pytest.mark.asyncio
async def test_send_telegram_message_allows_reply_to_within_history():
    from dataclasses import dataclass

    @dataclass
    class FakeMsg:
        id: int

    class FakeTelegram:
        async def get_chat_history(self, chat_id, limit=30):
            return [FakeMsg(id=555), FakeMsg(id=556)]

        async def send_message(self, chat_id, text, reply_to_message_id=None):
            return FakeMsg(id=999)

        async def send_typing(self, chat_id):
            pass

    chat = TelegramChat(id=111, title="Alice", type="private")
    tool = create_send_telegram_message_tool(FakeTelegram(), chat, recent_bot_messages=[])
    ctx = ToolContext(
        args={"text": "hi", "reply_to": 555},
        logger=logging.getLogger("test"),
        temporary_context=[],
    )
    result = await tool.handler(ctx)
    assert "message_id=999" in result


@pytest.mark.asyncio
async def test_get_telegram_chats_returns_string_not_raw_dataclasses():
    """Regression test: handlers used to return raw TelegramChat/TelegramMessage
    dataclasses, which crashed json.dumps() inside handle_tool_calls with
    'Object of type TelegramChat is not JSON serializable' -- causing every
    successful action to look like a failure to the LLM, which then retried
    it (duplicate sends, duplicate replies, etc)."""
    from src.tools import OpenAITools, create_get_telegram_chats_tool

    class FakeTelegram:
        async def get_chats(self, limit=50):
            return [TelegramChat(id=1, title="Alice", type="private", unread_count=2)]

    tools = OpenAITools()
    tools.insert(create_get_telegram_chats_tool(FakeTelegram()))
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "get_telegram_chats", "arguments": "{}"}}]
    results = await tools.handle_tool_calls(tool_calls, [])
    assert len(results) == 1
    assert "Error" not in results[0].content
    assert "Alice" in results[0].content


@pytest.mark.asyncio
async def test_react_forward_edit_remove_tools_return_confirmation_strings():
    from src.tools import (
        create_edit_message_tool,
        create_forward_message_tool,
        create_react_with_emoji_tool,
        create_remove_message_tool,
    )

    class FakeTelegram:
        async def react_with_emoji(self, chat_id, message_id, emoji):
            return None

        async def forward_message(self, from_chat_id, message_id, to_chat_id):
            return None

        async def edit_message_text(self, chat_id, message_id, new_text):
            return None

        async def delete_message(self, chat_id, message_id):
            return None

    telegram = FakeTelegram()
    cases = [
        (create_react_with_emoji_tool(telegram), {"chat_id": 1, "message_id": 2, "emoji": "😊"}),
        (create_forward_message_tool(telegram), {"from_chat_id": 1, "message_id": 2, "to_chat_id": 3}),
        (create_edit_message_tool(telegram), {"chat_id": 1, "message_id": 2, "new_text": "hi"}),
        (create_remove_message_tool(telegram), {"chat_id": 1, "message_id": 2}),
    ]
    for tool, args in cases:
        ctx = ToolContext(args=args, logger=logging.getLogger("test"), temporary_context=[])
        result = await tool.handler(ctx)
        assert isinstance(result, str) and result  # never None, never a raw object
