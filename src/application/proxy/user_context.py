"""User context management for multi-user proxy scenarios.

Обеспечивает изоляцию контекста между пользователями для multi-tenant deployment.
Phase 5: Open-LLM-VTuber Integration
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...openai_chat import Message
    from .session_manager import SessionManager

from .session_manager import ProxySession

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """Per-user context isolation.

    Ensures session data separation between different users.
    Each user has independent session namespace.
    """

    user_id: str
    sessions: dict[str, ProxySession] = field(default_factory=dict)  # session_id → session
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def is_inactive(self, timeout: timedelta) -> bool:
        """Check if user context is inactive.

        Args:
            timeout: Inactivity timeout duration

        Returns:
            True if user has been inactive for longer than timeout
        """
        return datetime.now(UTC) - self.last_activity > timeout


class UserContextManager:
    """Manage isolated contexts per user.

    Ensures:
    - Session isolation: User A cannot access User B's sessions
    - Memory isolation: Hidden context separated per user
    - Rate limit tracking: Per-user counters (future integration)

    Architecture:
        UserContextManager wraps SessionManager
        Each user gets isolated session namespace
        Fingerprints scoped per user: {user_id}:{fingerprint}
    """

    def __init__(self, session_manager: SessionManager):
        """Initialize user context manager.

        Args:
            session_manager: Underlying session manager for per-user sessions
        """
        self._session_manager = session_manager
        self._users: dict[str, UserContext] = {}
        self._lock = asyncio.Lock()
        logger.info("UserContextManager initialized")

    async def get_user_context(self, user_id: str) -> UserContext:
        """Get or create user context.

        Thread-safe creation of user contexts.

        Args:
            user_id: User identifier

        Returns:
            UserContext for the user
        """
        async with self._lock:
            if user_id not in self._users:
                self._users[user_id] = UserContext(user_id=user_id)
                logger.info(f"Created context for user: {user_id}")

            context = self._users[user_id]
            context.update_activity()
            return context

    async def get_user_session(
        self,
        user_id: str,
        messages: list[Message],
    ) -> ProxySession:
        """Get session for user, ensuring isolation.

        Scopes session lookup within user's namespace.
        Fingerprints are user-scoped to prevent cross-user collisions.

        Args:
            user_id: User identifier
            messages: Message array for session fingerprinting

        Returns:
            ProxySession isolated to this user
        """
        context = await self.get_user_context(user_id)

        # Generate user-scoped fingerprint
        base_fingerprint = self._session_manager.generate_fingerprint(messages)
        scoped_fingerprint = f"{user_id}:{base_fingerprint}"

        # Check if session exists in user's namespace
        if scoped_fingerprint in context.sessions:
            session = context.sessions[scoped_fingerprint]
            session.update_activity()
            logger.debug(f"Retrieved existing session for user {user_id}: {scoped_fingerprint}")
            return session

        # Try to find continuation session
        continuation = await self._find_user_continuation(
            context, scoped_fingerprint, messages
        )
        if continuation:
            logger.debug(
                f"Found continuation session for user {user_id}: {continuation.session_id}"
            )
            return continuation

        # Create new session for user
        session = ProxySession(
            session_id=scoped_fingerprint,
            user_id=user_id,
            messages=messages.copy(),
        )
        context.sessions[scoped_fingerprint] = session
        logger.info(f"Created new session for user {user_id}: {scoped_fingerprint}")

        return session

    async def _find_user_continuation(
        self,
        context: UserContext,
        fingerprint: str,
        messages: list[Message],
    ) -> ProxySession | None:
        """Find continuation session within user's namespace.

        Args:
            context: User context to search within
            fingerprint: Current request fingerprint
            messages: Current message array

        Returns:
            Continuation session if found, None otherwise
        """
        # Search only within user's sessions
        for session in context.sessions.values():
            # Check if current fingerprint is continuation of existing session
            existing_fingerprint = self._session_manager.generate_fingerprint(
                session.messages
            )
            if fingerprint.endswith(existing_fingerprint):
                # Update session with new messages
                session.messages = messages.copy()
                session.update_activity()
                return session

        return None

    async def cleanup_inactive_users(self, timeout: timedelta) -> int:
        """Remove inactive user contexts.

        Cleans up users who have not had activity for specified timeout.
        Used for memory management in long-running proxy instances.

        Args:
            timeout: Inactivity timeout duration

        Returns:
            Number of users removed
        """
        async with self._lock:
            inactive_users = [
                user_id
                for user_id, context in self._users.items()
                if context.is_inactive(timeout)
            ]

            for user_id in inactive_users:
                del self._users[user_id]
                logger.info(f"Cleaned up inactive user: {user_id}")

            if inactive_users:
                logger.info(f"Cleaned up {len(inactive_users)} inactive user(s)")

            return len(inactive_users)

    def get_user_count(self) -> int:
        """Get active user count for monitoring.

        Returns:
            Number of active users
        """
        return len(self._users)

    def get_user_session_count(self, user_id: str) -> int:
        """Get session count for specific user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions for user, 0 if user not found
        """
        context = self._users.get(user_id)
        return len(context.sessions) if context else 0

    async def get_all_users(self) -> list[str]:
        """Get all active user IDs.

        Returns:
            List of active user IDs
        """
        async with self._lock:
            return list(self._users.keys())
