"""Message injection for hidden tool call context.

Реализует паттерн MessageInjector из оригинального Kuni C++:
- Скрывает tool calls от клиента
- Автоматически инжектит скрытый контекст при продолжении сессии
- Позволяет multi-turn диалогам работать прозрачно через прокси
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...openai_chat import Message

if TYPE_CHECKING:
    from .session_manager import SessionManager

logger = logging.getLogger(__name__)


class MessageInjector:
    """Injects hidden tool call context into message history.

    Responsibilities:
    - Store tool calls and results as hidden context
    - Merge hidden context back into message history
    - Enable transparent multi-turn conversations

    Основано на MessageInjector из proxy_server.cpp:
    - Хранит assistant message + tool results по fingerprint'у
    - При следующем запросе инжектит их обратно
    - Клиент не видит промежуточные tool calls
    """

    def __init__(self, session_manager: SessionManager):
        """Initialize message injector.

        Args:
            session_manager: Session manager for context storage
        """
        self._sessions = session_manager
        logger.info("MessageInjector initialized")

    def merge_hidden_context(
        self,
        messages: list[Message],
        session_id: str,
    ) -> list[Message]:
        """Merge hidden tool call context into message history.

        Вставляет скрытые tool calls между visible messages:
        - Находит injection point (последнее assistant message)
        - Вставляет accumulated hidden context
        - Возвращает полную историю с tool calls

        Args:
            messages: Visible message history from client
            session_id: Session identifier

        Returns:
            Complete message history with hidden context
        """
        # Get session
        if session_id not in self._sessions._sessions:
            logger.debug(f"No hidden context for session {session_id[:8]}...")
            return messages

        session = self._sessions._sessions[session_id]
        if not session.hidden_context:
            logger.debug(f"Session {session_id[:8]}... has no hidden context")
            return messages

        # Find injection point (last assistant message from client)
        injection_index = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "assistant":
                injection_index = i + 1
                break

        # If no assistant message, inject at end
        if injection_index is None:
            logger.debug("No injection point found, appending to end")
            return messages + session.hidden_context

        # Inject hidden context after last assistant message
        merged = messages[:injection_index] + session.hidden_context + messages[injection_index:]

        logger.info(
            f"Merged {len(session.hidden_context)} hidden messages "
            f"into session {session_id[:8]}... at position {injection_index}"
        )

        return merged

    def store_tool_context(
        self,
        session_id: str,
        assistant_msg: Message,
        tool_results: list[Message],
    ) -> None:
        """Store tool calls and results as hidden context.

        Сохраняет:
        - Assistant message с tool_calls
        - Tool result messages

        Этот контекст будет автоматически инжектен при следующем запросе.

        Args:
            session_id: Session identifier
            assistant_msg: Assistant message with tool_calls
            tool_results: Tool result messages
        """
        if session_id not in self._sessions._sessions:
            logger.warning(f"Cannot store context for unknown session {session_id[:8]}...")
            return

        session = self._sessions._sessions[session_id]

        # Store assistant message with tool calls
        session.hidden_context.append(assistant_msg)

        # Store tool results
        session.hidden_context.extend(tool_results)

        logger.info(
            f"Stored hidden context for session {session_id[:8]}...: "
            f"1 assistant message + {len(tool_results)} tool results"
        )

    def clear_hidden_context(self, session_id: str) -> None:
        """Clear hidden context for session.

        Используется когда клиент начинает новый диалог
        и старый контекст больше не нужен.

        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions._sessions:
            session = self._sessions._sessions[session_id]
            cleared_count = len(session.hidden_context)
            session.hidden_context.clear()
            logger.debug(f"Cleared {cleared_count} hidden messages from session {session_id[:8]}...")

    def get_hidden_context_size(self, session_id: str) -> int:
        """Get number of hidden messages in session.

        Args:
            session_id: Session identifier

        Returns:
            Number of hidden messages
        """
        if session_id not in self._sessions._sessions:
            return 0

        return len(self._sessions._sessions[session_id].hidden_context)
