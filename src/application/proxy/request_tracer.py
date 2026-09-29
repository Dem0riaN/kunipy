"""Request tracing for proxy server.

Структурированное логирование запросов для отладки и аудита.
Основано на RequestTrace из оригинального Kuni.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RequestTracer:
    """Traces proxy requests for debugging and audit.

    Responsibilities:
    - Log request/response flow
    - Track client→proxy→llm→proxy→client
    - Support structured logging
    - Manage log file lifecycle

    Основано на RequestTrace из proxy_server.cpp:
    - Логирует каждый этап с timestamps
    - Разделяет client/kuni/llm потоки
    - Сохраняет в отдельные файлы по сессиям
    """

    def __init__(self, log_dir: Path | str = Path("logs_proxy")):
        """Initialize request tracer.

        Args:
            log_dir: Directory for trace logs (default: logs_proxy)
        """
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"RequestTracer initialized, logs in {self._log_dir}")

    def trace_request(
        self,
        direction: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Trace a request/response.

        Args:
            direction: Flow direction (client→proxy, proxy→llm, llm→proxy, proxy→client)
            payload: Request/response payload
            session_id: Optional session identifier
        """
        try:
            timestamp = datetime.now(UTC)
            ts_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")

            # Build filename
            filename = f"{ts_str}_{direction.replace('→', '_to_')}"
            if session_id:
                filename += f"_{session_id[:8]}"
            filename += ".json"

            # Write to file
            path = self._log_dir / filename
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            logger.debug(f"Traced {direction}: {path.name}")

        except (OSError, ValueError) as e:
            logger.debug(f"Failed to trace {direction}: {e}")

    def trace_client_to_proxy(
        self,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Trace client→proxy request.

        Args:
            payload: Request payload
            session_id: Optional session identifier
        """
        self.trace_request("client→proxy", payload, session_id)

    def trace_proxy_to_llm(
        self,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Trace proxy→llm request.

        Args:
            payload: Request payload
            session_id: Optional session identifier
        """
        self.trace_request("proxy→llm", payload, session_id)

    def trace_llm_to_proxy(
        self,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Trace llm→proxy response.

        Args:
            payload: Response payload
            session_id: Optional session identifier
        """
        self.trace_request("llm→proxy", payload, session_id)

    def trace_proxy_to_client(
        self,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        """Trace proxy→client response.

        Args:
            payload: Response payload
            session_id: Optional session identifier
        """
        self.trace_request("proxy→client", payload, session_id)

    def cleanup_old_logs(self, keep_days: int = 7) -> int:
        """Remove logs older than specified days.

        Args:
            keep_days: Keep logs for this many days (default: 7)

        Returns:
            Number of files removed
        """
        try:
            cutoff = datetime.now(UTC).timestamp() - (keep_days * 86400)
            removed = 0

            for path in self._log_dir.glob("*.json"):
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1

            if removed > 0:
                logger.info(f"Cleaned up {removed} old trace logs (>{keep_days} days)")

            return removed

        except OSError as e:
            logger.error(f"Failed to cleanup logs: {e}")
            return 0
