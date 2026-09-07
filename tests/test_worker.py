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


def test_trim_history_keeps_all_when_under_limit():
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
