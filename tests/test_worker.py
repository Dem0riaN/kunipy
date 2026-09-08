"""Tests for worker.py: history trimming by character budget."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config  # noqa: E402
from src.notification_manager import NotificationManager  # noqa: E402
from src.openai_chat import Message  # noqa: E402
from src.worker import Worker  # noqa: E402


def _make_worker(chat_max_history_length: int) -> Worker:
    config = Config()
    config.chat_max_history_length = chat_max_history_length
    worker = Worker(
        name="test-worker",
        app_base=None,
        telegram=None,
        openai=None,
        diary=None,
        notification_manager=NotificationManager(),
    )
    worker.config = config
    return worker


def test_log_assistant_turn_prints_thinking_and_tool_calls(caplog):
    worker = _make_worker(chat_max_history_length=1000)
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "send_telegram_message", "arguments": '{"text": "hi"}'}}]
    with caplog.at_level("INFO"):
        worker._log_assistant_turn(chat_id=42, content="thought: say hi", tool_calls=tool_calls)
    text = caplog.text
    assert "[chat_42]" in text
    assert "thinking: thought: say hi" in text
    assert 'send_telegram_message({"text": "hi"})' in text


def test_log_assistant_turn_skips_empty_content(caplog):
    worker = _make_worker(chat_max_history_length=1000)
    with caplog.at_level("INFO"):
        worker._log_assistant_turn(chat_id=42, content="", tool_calls=None)
    assert "thinking:" not in caplog.text


def test_log_tool_results_matches_call_names_by_id(caplog):
    worker = _make_worker(chat_max_history_length=1000)
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "send_telegram_message"}}]
    results = [Message(role="tool", content="Message sent successfully.", tool_call_id="c1")]
    with caplog.at_level("INFO"):
        worker._log_tool_results(chat_id=42, tool_calls=tool_calls, tool_results=results)
    assert "send_telegram_message: Message sent successfully." in caplog.text


def test_log_tool_results_truncates_long_output(caplog):
    worker = _make_worker(chat_max_history_length=1000)
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "web_search"}}]
    results = [Message(role="tool", content="x" * 500, tool_call_id="c1")]
    with caplog.at_level("INFO"):
        worker._log_tool_results(chat_id=42, tool_calls=tool_calls, tool_results=results)
    assert "\u2026" in caplog.text
    worker = _make_worker(chat_max_history_length=1000)
    messages = [Message(role="user", content="short") for _ in range(5)]
    trimmed = worker._trim_history(messages)
    assert trimmed == messages


def test_trim_history_drops_oldest_when_over_limit():
    worker = _make_worker(chat_max_history_length=25)
    messages = [
        Message(role="user", content="a" * 10),
        Message(role="assistant", content="b" * 10),
        Message(role="user", content="c" * 10),
    ]
    trimmed = worker._trim_history(messages)
    # Only the most recent messages that fit under the 25-char budget survive.
    assert trimmed[-1].content == "c" * 10
    assert messages[0] not in trimmed


def test_trim_history_always_keeps_at_least_the_last_message():
    worker = _make_worker(chat_max_history_length=1)
    messages = [Message(role="user", content="a" * 500)]
    trimmed = worker._trim_history(messages)
    assert len(trimmed) == 1


def test_trim_history_unlimited_when_zero():
    worker = _make_worker(chat_max_history_length=0)
    messages = [Message(role="user", content="x" * 10000) for _ in range(50)]
    trimmed = worker._trim_history(messages)
    assert len(trimmed) == 50
