"""Unit tests for proxy message injector."""

import pytest

from src.application.proxy.message_injector import MessageInjector
from src.application.proxy.session_manager import SessionManager
from src.openai_chat import Message


@pytest.fixture
def session_manager():
    """Create session manager for tests."""
    return SessionManager()


@pytest.fixture
def message_injector(session_manager):
    """Create message injector for tests."""
    return MessageInjector(session_manager)


def test_message_injector_initialization(message_injector):
    """Test message injector initialization."""
    assert message_injector is not None


def test_merge_hidden_context_no_session(message_injector):
    """Test merge with no existing session."""
    messages = [Message(role="user", content="Hello")]
    merged = message_injector.merge_hidden_context(messages, "nonexistent")

    # Should return original messages
    assert len(merged) == 1
    assert merged[0].content == "Hello"


def test_store_and_merge_hidden_context(session_manager, message_injector):
    """Test storing and merging hidden context."""
    # Create session
    messages = [Message(role="user", content="Hello")]
    session = session_manager.get_or_create(messages)

    # Store hidden context
    assistant_msg = Message(
        role="assistant",
        content="Let me help",
        tool_calls=[{"id": "call_1", "function": {"name": "ask", "arguments": "{}"}}],
    )
    tool_result = Message(role="tool", content="Result", tool_call_id="call_1")

    message_injector.store_tool_context(session.session_id, assistant_msg, [tool_result])

    # Verify stored
    assert message_injector.get_hidden_context_size(session.session_id) == 2

    # Merge back
    new_messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi"),
    ]
    merged = message_injector.merge_hidden_context(new_messages, session.session_id)

    # Should include hidden context
    assert len(merged) > len(new_messages)
    assert any(msg.role == "tool" for msg in merged)


def test_clear_hidden_context(session_manager, message_injector):
    """Test clearing hidden context."""
    # Create session with hidden context
    messages = [Message(role="user", content="Hello")]
    session = session_manager.get_or_create(messages)

    assistant_msg = Message(role="assistant", content="Test")
    message_injector.store_tool_context(session.session_id, assistant_msg, [])

    assert message_injector.get_hidden_context_size(session.session_id) == 1

    # Clear
    message_injector.clear_hidden_context(session.session_id)

    assert message_injector.get_hidden_context_size(session.session_id) == 0


def test_hidden_context_size_unknown_session(message_injector):
    """Test getting size for unknown session."""
    size = message_injector.get_hidden_context_size("unknown")
    assert size == 0


def test_injection_point_after_assistant(session_manager, message_injector):
    """Test injection point is after last assistant message."""
    messages = [Message(role="user", content="Hello")]
    session = session_manager.get_or_create(messages)

    # Store hidden context
    assistant_msg = Message(role="assistant", content="Hidden", tool_calls=[])
    tool_result = Message(role="tool", content="Tool result", tool_call_id="call_1")
    message_injector.store_tool_context(session.session_id, assistant_msg, [tool_result])

    # Messages with assistant at index 1
    visible_messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Visible"),
        Message(role="user", content="More"),
    ]

    merged = message_injector.merge_hidden_context(visible_messages, session.session_id)

    # Hidden context should be after assistant message (index 1)
    # Find where tool message appears
    tool_indices = [i for i, msg in enumerate(merged) if msg.role == "tool"]
    assert len(tool_indices) > 0
    assert tool_indices[0] > 1  # After assistant at index 1


def test_multiple_tool_results(session_manager, message_injector):
    """Test storing multiple tool results."""
    messages = [Message(role="user", content="Hello")]
    session = session_manager.get_or_create(messages)

    assistant_msg = Message(role="assistant", content="Processing")
    tool_results = [
        Message(role="tool", content="Result 1", tool_call_id="call_1"),
        Message(role="tool", content="Result 2", tool_call_id="call_2"),
    ]

    message_injector.store_tool_context(session.session_id, assistant_msg, tool_results)

    # Should have 1 assistant + 2 tool results = 3 hidden messages
    assert message_injector.get_hidden_context_size(session.session_id) == 3


def test_store_context_unknown_session(message_injector):
    """Test storing context for unknown session (should handle gracefully)."""
    assistant_msg = Message(role="assistant", content="Test")

    # Should not crash
    message_injector.store_tool_context("unknown", assistant_msg, [])

    # Size should still be 0 (session doesn't exist)
    assert message_injector.get_hidden_context_size("unknown") == 0
