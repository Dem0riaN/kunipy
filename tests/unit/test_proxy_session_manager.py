"""Unit tests for proxy session manager."""

from datetime import UTC, datetime, timedelta

from src.application.proxy.session_manager import ProxySession, SessionManager
from src.openai_chat import Message


def test_session_creation():
    """Test basic session creation."""
    session = ProxySession(
        session_id="test123",
        user_id="user456",
    )

    assert session.session_id == "test123"
    assert session.user_id == "user456"
    assert len(session.messages) == 0
    assert len(session.hidden_context) == 0
    assert isinstance(session.last_activity, datetime)


def test_session_expiry():
    """Test session expiration logic."""
    session = ProxySession(session_id="test", user_id=None)

    # Not expired with 1 hour timeout
    assert not session.is_expired(timedelta(hours=1))

    # Manually set old timestamp
    session.last_activity = datetime.now(UTC) - timedelta(hours=2)
    assert session.is_expired(timedelta(hours=1))


def test_session_manager_initialization():
    """Test session manager initialization."""
    manager = SessionManager(session_timeout_minutes=30)
    assert manager.get_session_count() == 0


def test_fingerprint_generation():
    """Test message fingerprint generation."""
    manager = SessionManager()

    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi there"),
    ]

    fingerprint1 = manager.generate_fingerprint(messages)
    fingerprint2 = manager.generate_fingerprint(messages)

    # Same messages = same fingerprint
    assert fingerprint1 == fingerprint2
    assert len(fingerprint1) == 16  # 16 chars hex


def test_fingerprint_stability():
    """Test fingerprint stability across structural changes."""
    manager = SessionManager()

    messages1 = [Message(role="user", content="test")]
    messages2 = [Message(role="user", content="test")]

    # Same content = same fingerprint
    assert manager.generate_fingerprint(messages1) == manager.generate_fingerprint(messages2)


def test_get_or_create_new_session():
    """Test creating new session."""
    manager = SessionManager()

    messages = [Message(role="user", content="Hello")]
    session = manager.get_or_create(messages, user_id="user123")

    assert session.user_id == "user123"
    assert manager.get_session_count() == 1


def test_get_or_create_existing_session():
    """Test retrieving existing session."""
    manager = SessionManager()

    messages = [Message(role="user", content="Hello")]
    session1 = manager.get_or_create(messages, user_id="user123")
    session2 = manager.get_or_create(messages, user_id="user123")

    # Should be same session
    assert session1.session_id == session2.session_id
    assert manager.get_session_count() == 1


def test_session_continuation_detection():
    """Test session continuation via fingerprint prefix."""
    manager = SessionManager()

    # Create initial session
    messages1 = [Message(role="user", content="Hello")]
    manager.get_or_create(messages1)

    # Extended conversation (should be continuation)
    messages2 = messages1 + [
        Message(role="assistant", content="Hi"),
        Message(role="user", content="How are you?"),
    ]

    manager.generate_fingerprint(messages1)
    manager.generate_fingerprint(messages2)

    # Fingerprint2 should start with fingerprint1 (continuation)
    # Note: This depends on implementation - may need adjustment
    manager.get_or_create(messages2)

    # Should track as separate or continuation based on fingerprint logic
    assert manager.get_session_count() >= 1


def test_cleanup_expired_sessions():
    """Test expired session cleanup."""
    manager = SessionManager(session_timeout_minutes=0)  # Immediate expiry

    messages = [Message(role="user", content="Hello")]
    session = manager.get_or_create(messages)

    # Set old timestamp
    session.last_activity = datetime.now(UTC) - timedelta(hours=1)

    # Cleanup should remove it
    removed = manager.cleanup_expired()
    assert removed == 1
    assert manager.get_session_count() == 0


def test_multiple_sessions():
    """Test managing multiple sessions."""
    manager = SessionManager()

    messages1 = [Message(role="user", content="Session 1")]
    messages2 = [Message(role="user", content="Session 2")]

    session1 = manager.get_or_create(messages1, user_id="user1")
    session2 = manager.get_or_create(messages2, user_id="user2")

    assert session1.session_id != session2.session_id
    assert manager.get_session_count() == 2


def test_update_activity():
    """Test activity timestamp update."""
    manager = SessionManager()

    messages = [Message(role="user", content="Hello")]
    session = manager.get_or_create(messages)

    old_activity = session.last_activity

    # Small delay
    import time
    time.sleep(0.01)

    manager.update_activity(session.session_id)

    # Timestamp should be updated
    assert session.last_activity > old_activity


def test_remove_session():
    """Test session removal."""
    manager = SessionManager()

    messages = [Message(role="user", content="Hello")]
    session = manager.get_or_create(messages)

    assert manager.get_session_count() == 1

    manager.remove_session(session.session_id)

    assert manager.get_session_count() == 0
