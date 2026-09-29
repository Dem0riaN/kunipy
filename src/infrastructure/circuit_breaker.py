"""Simple circuit breaker for external service calls.

Implements circuit breaker pattern to prevent cascading failures
and improve system resilience.

Based on Martin Fowler's Circuit Breaker pattern.
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Blocking calls (service down)
    HALF_OPEN = "half_open"    # Testing recovery


class CircuitBreaker:
    """Simple circuit breaker for service reliability.

    Tracks failures and opens circuit to prevent cascading failures.
    When circuit is open, calls fail fast without hitting the service.

    State transitions:
    - CLOSED → OPEN: After failure_threshold consecutive failures
    - OPEN → HALF_OPEN: After timeout seconds
    - HALF_OPEN → CLOSED: After successful test call
    - HALF_OPEN → OPEN: On any failure
    """

    def __init__(
        self,
        name: str = "unnamed",
        failure_threshold: int = 5,
        timeout: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker name (for logging)
            failure_threshold: Failures before opening circuit
            timeout: Seconds before attempting recovery (OPEN → HALF_OPEN)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._success_count = 0
        self._total_calls = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Current failure count."""
        return self._failure_count

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        return self._state == CircuitState.OPEN

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute function through circuit breaker.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            RuntimeError: If circuit is open
            Original exception: If function fails
        """
        self._total_calls += 1

        # Check if circuit should transition to half-open
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info(f"Circuit breaker '{self.name}': Attempting recovery (OPEN → HALF_OPEN)")
                self._state = CircuitState.HALF_OPEN
            else:
                raise RuntimeError(
                    f"Circuit breaker '{self.name}' is OPEN "
                    f"(threshold: {self.failure_threshold} failures, "
                    f"retry in {self._time_until_retry():.1f}s)"
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result

        except Exception as e:
            self._on_failure(e)
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try recovery."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.timeout

    def _time_until_retry(self) -> float:
        """Calculate seconds until retry is allowed."""
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.timeout - elapsed)

    def _on_success(self) -> None:
        """Handle successful call."""
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                f"Circuit breaker '{self.name}': Service recovered (HALF_OPEN → CLOSED)"
            )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def _on_failure(self, error: Exception) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during recovery test - go back to OPEN
            logger.warning(
                f"Circuit breaker '{self.name}': Recovery failed, "
                f"reopening circuit (HALF_OPEN → OPEN)"
            )
            self._state = CircuitState.OPEN

        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                logger.error(
                    f"Circuit breaker '{self.name}': Opening circuit after "
                    f"{self._failure_count} failures (CLOSED → OPEN). "
                    f"Error: {error}"
                )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        logger.info(f"Circuit breaker '{self.name}': Manual reset to CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics.

        Returns:
            Dictionary with state, counts, and timing info
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self._total_calls,
            "failure_threshold": self.failure_threshold,
            "timeout": self.timeout,
            "time_until_retry": self._time_until_retry() if self._state == CircuitState.OPEN else 0.0,
        }
