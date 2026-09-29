"""Rate limiting for proxy server per-user protection.

Предотвращает злоупотребление ресурсами через per-user rate limiting.
Phase 5: Open-LLM-VTuber Integration
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration.

    Defines limits for requests per time window.
    """

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Allow short bursts above per-minute rate


@dataclass
class RateLimitState:
    """Per-user rate limit state.

    Tracks request counts in sliding time windows.
    """

    user_id: str
    minute_count: int = 0
    hour_count: int = 0
    minute_window_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    hour_window_start: datetime = field(default_factory=lambda: datetime.now(UTC))

    def reset_minute_window(self) -> None:
        """Reset minute window counter."""
        self.minute_count = 0
        self.minute_window_start = datetime.now(UTC)

    def reset_hour_window(self) -> None:
        """Reset hour window counter."""
        self.hour_count = 0
        self.hour_window_start = datetime.now(UTC)


class RateLimiter:
    """Token bucket rate limiter per user.

    Implements:
    - Requests per minute limit
    - Requests per hour limit
    - Burst allowance
    - Sliding window algorithm

    Algorithm:
        1. Check if time windows have expired
        2. Reset counters for expired windows
        3. Check if request would exceed limits
        4. Record request if allowed
    """

    def __init__(self, config: RateLimitConfig):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration
        """
        self._config = config
        self._states: dict[str, RateLimitState] = {}
        self._lock = asyncio.Lock()
        logger.info(
            f"RateLimiter initialized: {config.requests_per_minute}/min, "
            f"{config.requests_per_hour}/hour, burst={config.burst_size}"
        )

    async def check_rate_limit(self, user_id: str) -> tuple[bool, str | None]:
        """Check if user can make request.

        Thread-safe check against rate limits.

        Args:
            user_id: User identifier

        Returns:
            Tuple of (allowed, error_message)
            - allowed: True if request is allowed
            - error_message: Error description if not allowed, None otherwise
        """
        async with self._lock:
            state = self._get_or_create_state(user_id)
            now = datetime.now(UTC)

            # Check and reset expired windows
            self._update_windows(state, now)

            # Check minute limit (with burst allowance)
            minute_limit = self._config.requests_per_minute + self._config.burst_size
            if state.minute_count >= minute_limit:
                seconds_until_reset = 60 - (now - state.minute_window_start).seconds
                error = (
                    f"Rate limit exceeded: {state.minute_count}/{minute_limit} requests/minute. "
                    f"Try again in {seconds_until_reset}s."
                )
                logger.warning(f"Rate limit exceeded for user {user_id}: {error}")
                return False, error

            # Check hour limit
            if state.hour_count >= self._config.requests_per_hour:
                minutes_until_reset = 60 - (now - state.hour_window_start).seconds // 60
                error = (
                    f"Rate limit exceeded: {state.hour_count}/{self._config.requests_per_hour} "
                    f"requests/hour. Try again in {minutes_until_reset}min."
                )
                logger.warning(f"Rate limit exceeded for user {user_id}: {error}")
                return False, error

            return True, None

    async def record_request(self, user_id: str) -> None:
        """Record successful request for user.

        Must be called after check_rate_limit() returns True.

        Args:
            user_id: User identifier
        """
        async with self._lock:
            state = self._get_or_create_state(user_id)
            state.minute_count += 1
            state.hour_count += 1
            logger.debug(
                f"Recorded request for user {user_id}: "
                f"{state.minute_count}/min, {state.hour_count}/hour"
            )

    async def get_user_stats(self, user_id: str) -> dict[str, int]:
        """Get rate limit stats for user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with current counts and limits
        """
        async with self._lock:
            state = self._states.get(user_id)
            if not state:
                return {
                    "minute_count": 0,
                    "minute_limit": self._config.requests_per_minute,
                    "hour_count": 0,
                    "hour_limit": self._config.requests_per_hour,
                }

            now = datetime.now(UTC)
            self._update_windows(state, now)

            return {
                "minute_count": state.minute_count,
                "minute_limit": self._config.requests_per_minute,
                "hour_count": state.hour_count,
                "hour_limit": self._config.requests_per_hour,
            }

    async def cleanup_expired_states(self) -> int:
        """Clean up old rate limit states.

        Removes states for users who haven't made requests recently.
        Frees memory in long-running proxy instances.

        Returns:
            Number of states removed
        """
        async with self._lock:
            now = datetime.now(UTC)
            expired_timeout = timedelta(hours=2)  # Keep states for 2 hours

            expired_users = [
                user_id
                for user_id, state in self._states.items()
                if (now - state.hour_window_start) > expired_timeout
            ]

            for user_id in expired_users:
                del self._states[user_id]
                logger.debug(f"Cleaned up rate limit state for user: {user_id}")

            if expired_users:
                logger.info(f"Cleaned up {len(expired_users)} expired rate limit state(s)")

            return len(expired_users)

    def _get_or_create_state(self, user_id: str) -> RateLimitState:
        """Get or create rate limit state for user.

        Args:
            user_id: User identifier

        Returns:
            RateLimitState for the user
        """
        if user_id not in self._states:
            self._states[user_id] = RateLimitState(user_id=user_id)
            logger.debug(f"Created rate limit state for user: {user_id}")

        return self._states[user_id]

    def _update_windows(self, state: RateLimitState, now: datetime) -> None:
        """Update time windows and reset counters if expired.

        Args:
            state: Rate limit state to update
            now: Current timestamp
        """
        # Check minute window
        minute_elapsed = (now - state.minute_window_start).total_seconds()
        if minute_elapsed >= 60:
            state.reset_minute_window()
            logger.debug(f"Reset minute window for user: {state.user_id}")

        # Check hour window
        hour_elapsed = (now - state.hour_window_start).total_seconds()
        if hour_elapsed >= 3600:
            state.reset_hour_window()
            logger.debug(f"Reset hour window for user: {state.user_id}")

    def get_active_user_count(self) -> int:
        """Get count of users with active rate limit states.

        Returns:
            Number of tracked users
        """
        return len(self._states)
