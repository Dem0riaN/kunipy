"""Session management for proxy server.

Управляет сессиями клиентов, отслеживает контекст и состояние.
Реализует fingerprint-based session tracking из оригинального Kuni.
Following ТЗ-001 §7 - Application layer service.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ...openai_chat import Message
from .core.models import SessionState

logger = logging.getLogger(__name__)


@dataclass
class ProxySession:
    """Proxy session state.

    Хранит контекст сессии клиента для multi-turn диалогов.
    Extended with state tracking for WebSocket support (ТЗ-001 Phase 2).
    """

    session_id: str  # Message fingerprint
    user_id: str | None
    messages: list[Message] = field(default_factory=list)
    hidden_context: list[Message] = field(default_factory=list)  # Tool calls + results
    state: SessionState = SessionState.IDLE
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def is_expired(self, timeout: timedelta) -> bool:
        """Check if session has expired.

        Args:
            timeout: Session timeout duration

        Returns:
            True if session expired
        """
        return datetime.now(UTC) - self.last_activity > timeout


class SessionManager:
    """Manages proxy sessions with fingerprint-based tracking.

    Responsibilities:
    - Create and track sessions
    - Generate message fingerprints
    - Detect session continuation
    - Session state management (idle/processing/interrupted)
    - Clean up expired sessions

    Following ТЗ-001 §7 - Application layer service.
    Extended with state tracking for WebSocket support (Phase 2).
    """

    def __init__(self, session_timeout_minutes: int = 30):
        """Initialize session manager.

        Args:
            session_timeout_minutes: Session timeout in minutes (default 30)
        """
        self._sessions: dict[str, ProxySession] = {}
        self._timeout = timedelta(minutes=session_timeout_minutes)
        logger.info(f"SessionManager initialized with {session_timeout_minutes}min timeout")

    def calculate_fingerprint(self, messages: list[Message]) -> str:
        """Calculate stable fingerprint for message array.

        Основано на json_fingerprint.h из оригинального Kuni:
        - Удаляет структурные символы для стабильности
        - Позволяет определить продолжение сессии через startswith()

        Args:
            messages: Message list to fingerprint

        Returns:
            Stable fingerprint string
        """
        # Convert Message objects to dicts if needed
        messages_data = []
        for msg in messages:
            if isinstance(msg, Message):
                messages_data.append(msg.to_dict())
            elif isinstance(msg, dict):
                messages_data.append(msg)
            else:
                raise TypeError(f"Expected Message or dict, got {type(msg)}")

        # Serialize messages to stable JSON
        serialized = json.dumps(messages_data, sort_keys=True, ensure_ascii=False)

        # Remove structural characters for stability
        # Оригинал: strips {,},[,],(,) для создания stable ID
        stable = serialized.replace("{", "").replace("}", "")
        stable = stable.replace("[", "").replace("]", "")
        stable = stable.replace("(", "").replace(")", "")
        stable = stable.replace(" ", "").replace("\n", "")

        # Hash for manageable size
        return hashlib.sha256(stable.encode()).hexdigest()[:16]

    def generate_fingerprint(self, messages: list[Message]) -> str:
        """Generate stable fingerprint for message array.

        Deprecated: Use calculate_fingerprint() instead.
        Kept for backward compatibility.

        Args:
            messages: Message list to fingerprint

        Returns:
            Stable fingerprint string
        """
        return self.calculate_fingerprint(messages)

    def get_or_create(
        self,
        messages: list[Message],
        user_id: str | None = None,
    ) -> ProxySession:
        """Get existing session or create new one.

        Использует fingerprint для определения продолжения сессии:
        - Если fingerprint совпадает - возвращает существующую сессию
        - Если fingerprint начинается с существующего - продолжение сессии
        - Иначе создаёт новую сессию

        Args:
            messages: Current message list
            user_id: Optional user identifier

        Returns:
            ProxySession instance
        """
        fingerprint = self.generate_fingerprint(messages)

        # Exact match
        if fingerprint in self._sessions:
            session = self._sessions[fingerprint]
            session.update_activity()
            logger.debug(f"Reusing session {fingerprint[:8]}...")
            return session

        # Check for session continuation (fingerprint.startsWith)
        for session_id, session in self._sessions.items():
            if fingerprint.startswith(session_id):
                session.update_activity()
                logger.debug(f"Continuing session {session_id[:8]}... -> {fingerprint[:8]}...")
                return session

        # Create new session
        session = ProxySession(
            session_id=fingerprint,
            user_id=user_id,
            messages=messages.copy(),
            metadata={"created_at": datetime.now(UTC).isoformat()},
        )
        self._sessions[fingerprint] = session
        logger.info(f"Created new session {fingerprint[:8]}... for user {user_id or 'anonymous'}")
        return session

    def update_activity(self, session_id: str) -> None:
        """Update session activity timestamp.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            self._sessions[session_id].update_activity()

    def get_expired_sessions(self) -> list[ProxySession]:
        """Get all expired sessions.

        Returns:
            List of expired sessions
        """
        expired = []
        for session in self._sessions.values():
            if session.is_expired(self._timeout):
                expired.append(session)
        return expired

    def remove_session(self, session_id: str) -> None:
        """Remove session from tracking.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Removed session {session_id[:8]}...")

    def cleanup_expired(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed
        """
        expired = self.get_expired_sessions()
        for session in expired:
            self.remove_session(session.session_id)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

        return len(expired)

    def get_all_sessions(self) -> list[ProxySession]:
        """Get all active sessions.

        Returns:
            List of all sessions
        """
        return list(self._sessions.values())

    def get_session_count(self) -> int:
        """Get current number of active sessions.

        Returns:
            Active session count
        """
        return len(self._sessions)

    def mark_processing(self, session_id: str) -> None:
        """Mark session as processing (conversation_active=True).

        Used by WebSocket adapter to prevent race conditions.
        Following ТЗ-001 Phase 2 - WebSocket support.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            self._sessions[session_id].state = SessionState.PROCESSING
            self._sessions[session_id].update_activity()
            logger.debug(f"Session {session_id[:8]}... marked as PROCESSING")

    def mark_idle(self, session_id: str) -> None:
        """Mark session as idle (conversation_active=False).

        Used by WebSocket adapter after conversation ends.
        Following ТЗ-001 Phase 2 - WebSocket support.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            self._sessions[session_id].state = SessionState.IDLE
            self._sessions[session_id].update_activity()
            logger.debug(f"Session {session_id[:8]}... marked as IDLE")

    def mark_interrupted(self, session_id: str) -> None:
        """Mark session as interrupted.

        Used by WebSocket adapter for interrupt-signal handling.
        Following ТЗ-001 Phase 2 - WebSocket support.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            self._sessions[session_id].state = SessionState.INTERRUPTED
            self._sessions[session_id].update_activity()
            logger.info(f"Session {session_id[:8]}... marked as INTERRUPTED")

    def get_session_state(self, session_id: str) -> SessionState | None:
        """Get current session state.

        Following ТЗ-001 Phase 2 - WebSocket support.

        Args:
            session_id: Session identifier

        Returns:
            Current session state or None if not found
        """
        if session_id in self._sessions:
            return self._sessions[session_id].state
        return None

    def get_session(self, session_id: str) -> ProxySession | None:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session or None if not found
        """
        return self._sessions.get(session_id)
