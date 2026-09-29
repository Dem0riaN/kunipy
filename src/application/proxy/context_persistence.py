"""Proxy context persistence service (Phase 4).

Auto-saves expired proxy sessions to diary using LLM summarization.
Implements feature parity with Kuni C++ ContextBridge.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...infrastructure.memory.diary_dump_service import DiaryDumpService
    from .session_manager import ProxySession, SessionManager

logger = logging.getLogger(__name__)


class ContextPersistence:
    """Auto-save expired proxy sessions to diary.

    Background task monitors SessionManager and saves expired sessions
    via DiaryDumpService LLM summarization. Implements Kuni C++ ContextBridge
    feature parity.

    Example:
        >>> persistence = ContextPersistence(
        ...     session_manager=session_mgr,
        ...     diary_dump_service=diary_dump,
        ...     check_interval_minutes=5,
        ...     session_timeout_minutes=30,
        ... )
        >>> await persistence.start()
        >>> # ... proxy server runs ...
        >>> await persistence.stop()
    """

    def __init__(
        self,
        session_manager: SessionManager,
        diary_dump_service: DiaryDumpService,
        check_interval_minutes: int = 5,
        session_timeout_minutes: int = 30,
    ):
        """Initialize context persistence service.

        Args:
            session_manager: Session manager instance
            diary_dump_service: Diary dump service for summarization
            check_interval_minutes: How often to check for expired sessions
            session_timeout_minutes: Session expiry threshold
        """
        self._session_manager = session_manager
        self._diary_dump = diary_dump_service
        self._check_interval = timedelta(minutes=check_interval_minutes)
        self._session_timeout = timedelta(minutes=session_timeout_minutes)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background persistence task."""
        if self._running:
            logger.warning("ContextPersistence already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._persistence_loop())
        logger.info(
            f"ContextPersistence started: check_interval={self._check_interval.total_seconds() / 60:.1f}m, "
            f"session_timeout={self._session_timeout.total_seconds() / 60:.1f}m"
        )

    async def stop(self) -> None:
        """Stop background persistence task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("ContextPersistence stopped")

    async def _persistence_loop(self) -> None:
        """Background loop checking for expired sessions."""
        while self._running:
            try:
                await self._check_and_save_expired()
            except Exception:
                logger.exception("Error in persistence loop")

            # Sleep until next check
            await asyncio.sleep(self._check_interval.total_seconds())

    async def _check_and_save_expired(self) -> None:
        """Check for expired sessions and save to diary."""
        now = datetime.now(UTC)
        expired_threshold = now - self._session_timeout

        # Get all sessions
        all_sessions = self._session_manager.get_all_sessions()

        expired_sessions = [s for s in all_sessions if s.last_activity < expired_threshold]

        if not expired_sessions:
            return

        logger.info(f"Found {len(expired_sessions)} expired sessions to save")

        for session in expired_sessions:
            try:
                await self._save_session_to_diary(session, now)

                # Remove from session manager after successful save
                self._session_manager.remove_session(session.session_id)

                inactive_minutes = (now - session.last_activity).total_seconds() / 60
                logger.info(
                    f"Saved and removed expired session: {session.session_id[:8]}... "
                    f"(inactive for {inactive_minutes:.1f} minutes)"
                )

            except Exception:
                logger.exception(f"Failed to save session {session.session_id[:8]}...")
                # Continue with next session (graceful degradation)

    async def _save_session_to_diary(self, session: ProxySession, now: datetime) -> None:
        """Save single session to diary via DiaryDumpService.

        Args:
            session: ProxySession to save
            now: Current timestamp for logging
        """
        # Convert session messages to format compatible with DiaryDumpService
        messages = []

        # Include visible messages
        for msg in session.messages:
            messages.append(
                {
                    "role": msg.role,
                    "content": msg.content or "",
                }
            )

        # Include hidden context (tool calls + results)
        for msg in session.hidden_context:
            msg_dict = {
                "role": msg.role,
                "content": msg.content or "",
            }

            # Add tool call metadata if present
            if msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id

            messages.append(msg_dict)

        if not messages:
            logger.debug(f"Session {session.session_id[:8]}... has no messages, skipping")
            return

        # Use chat_id from session metadata or generate from user_id
        chat_id = session.metadata.get("chat_id")
        if not chat_id and session.user_id:
            # Use numeric hash of user_id as chat_id for diary
            chat_id = abs(hash(session.user_id)) % (10**10)
        else:
            chat_id = 0  # Default chat_id

        logger.debug(
            f"Saving session {session.session_id[:8]}... to diary: "
            f"{len(messages)} messages, chat_id={chat_id}"
        )

        # DiaryDumpService will handle LLM summarization and diary write
        await self._diary_dump.maybe_dump(messages, chat_id)
