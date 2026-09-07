"""Tests for notification_manager.py: priority ordering and handler dispatch."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.notification_manager import Notification, NotificationManager  # noqa: E402


@pytest.mark.asyncio
async def test_priority_ordering():
    nm = NotificationManager()
    nm.start(worker_count=1)
    try:
        nm.add_notification(Notification(message="low", priority=1, pin="chat_1"))
        nm.add_notification(Notification(message="high", priority=10, pin="chat_1"))
        nm.add_notification(Notification(message="mid", priority=5, pin="chat_1"))

        first = await nm.get()
        second = await nm.get()
        third = await nm.get()

        assert [first.message, second.message, third.message] == ["high", "mid", "low"]
    finally:
        nm.stop()


@pytest.mark.asyncio
async def test_sync_handler_is_called():
    nm = NotificationManager()
    nm.start(worker_count=1)
    seen = []
    nm.register_handler(lambda n: seen.append(n.message))
    try:
        nm.add_notification(Notification(message="hello", pin="chat_2"))
        await nm.get()
        assert seen == ["hello"]
    finally:
        nm.stop()


@pytest.mark.asyncio
async def test_async_handler_is_awaited():
    """Regression test: async handlers must actually run, not just be scheduled."""
    nm = NotificationManager()
    nm.start(worker_count=1)
    seen = []

    async def handler(notification: Notification) -> None:
        seen.append(notification.message)

    nm.register_handler(handler)
    try:
        nm.add_notification(Notification(message="async-hello", pin="chat_3"))
        await nm.get()
        assert seen == ["async-hello"]
    finally:
        nm.stop()


@pytest.mark.asyncio
async def test_handler_exception_does_not_break_get():
    nm = NotificationManager()
    nm.start(worker_count=1)

    def bad_handler(_notification: Notification) -> None:
        raise RuntimeError("boom")

    nm.register_handler(bad_handler)
    try:
        nm.add_notification(Notification(message="still works", pin="chat_4"))
        result = await nm.get()
        assert result is not None
        assert result.message == "still works"
    finally:
        nm.stop()
