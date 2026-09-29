"""Protocol-agnostic proxy core service.

Orchestrates proxy business logic independent of transport protocol.
Following ТЗ-001 architecture principles:
- Application layer service (§7)
- Dependency injection (§8)
- No protocol-specific code (REST/WebSocket agnostic)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ....openai_chat import Message
from .models import FilteredResponse, UserContext

if TYPE_CHECKING:
    from ...config import Config
    from ...infrastructure.memory.diary_context_injector import DiaryContextInjector
    from ..message_injector import MessageInjector
    from ..session_manager import SessionManager
    from ..tool_provider import ProxyToolProvider
    from .context import ContextManager
    from .thinking_filter import ThinkingFilter

logger = logging.getLogger(__name__)


class ProxyCoreService:
    """Protocol-agnostic proxy core service.

    Responsibilities:
    - Session lifecycle management
    - Message processing pipeline
    - Tool execution loop
    - Memory & diary integration
    - Response filtering

    Architecture (ТЗ-001 §7):
    - Application layer - business logic
    - Composed from injected services
    - No transport protocol awareness
    """

    def __init__(
        self,
        config: Config,
        session_manager: SessionManager,
        message_injector: MessageInjector,
        tool_provider: ProxyToolProvider,
        context_manager: ContextManager,
        thinking_filter: ThinkingFilter,
        diary_injector: DiaryContextInjector | None = None,
    ):
        """Initialize proxy core service.

        All dependencies injected (ТЗ-001 §8).

        Args:
            config: Application config
            session_manager: Session tracking
            message_injector: Hidden context injection
            tool_provider: Tool registry
            context_manager: User context resolution
            thinking_filter: Thinking filtering strategy
            diary_injector: Diary context injector (optional)
        """
        self._config = config
        self._sessions = session_manager
        self._injector = message_injector
        self._tools = tool_provider
        self._context = context_manager
        self._thinking = thinking_filter
        self._diary = diary_injector
        logger.info("ProxyCoreService initialized")

    async def resolve_user_context(
        self,
        user_id: str,
        headers: dict[str, str],
    ) -> UserContext:
        """Resolve user context from headers.

        Delegates to ContextManager (ТЗ-001 §8 - Separation of concerns).

        Args:
            user_id: User identifier
            headers: Request headers

        Returns:
            UserContext with papik identification and memory
        """
        return await self._context.resolve_user_context(user_id, headers)

    def build_system_prompt(
        self,
        user_context: UserContext,
        diary_context: str = "",
    ) -> str:
        """Build system prompt with user context.

        Delegates to ContextManager (ТЗ-001 §8).

        Args:
            user_context: User context
            diary_context: Diary RAG context

        Returns:
            Complete system prompt
        """
        return self._context.build_system_prompt(user_context, diary_context)

    async def inject_diary_context(
        self,
        messages: list[Message],
    ) -> str:
        """Inject diary context for last user message.

        Args:
            messages: Message history

        Returns:
            Diary RAG context string
        """
        if not self._diary or not self._config.diary_auto_rag_enabled:
            return ""

        try:
            # Get last user message
            last_user_msg = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_user_msg = msg
                    break

            if not last_user_msg or not last_user_msg.content:
                return ""

            # Inject diary context using inject_into_system_prompt method
            # This returns a formatted string (lines joined with \n)
            context = await self._diary.inject_into_system_prompt(last_user_msg.content)

            # Ensure context is a string
            if context is None:
                context = ""
            elif isinstance(context, list):
                context = "\n".join(str(item) for item in context)
            elif not isinstance(context, str):
                context = str(context)

            if context:
                logger.info(f"Injected diary context ({len(context)} chars)")
            return context

        except Exception as e:
            logger.error(f"Failed to inject diary context: {e}", exc_info=True)
            return ""

    def filter_response(self, content: str) -> FilteredResponse:
        """Filter thinking from LLM response.

        Delegates to ThinkingFilter (ТЗ-001 §8).

        Args:
            content: Raw LLM response

        Returns:
            FilteredResponse with thinking separated
        """
        return self._thinking.filter_response(content)

    def merge_hidden_context(
        self,
        messages: list[Message],
        session_id: str,
    ) -> list[Message]:
        """Merge hidden context into messages.

        Delegates to MessageInjector (ТЗ-001 §8).

        Args:
            messages: Original messages
            session_id: Session identifier

        Returns:
            Messages with hidden context merged
        """
        return self._injector.merge_hidden_context(messages, session_id)

    def store_hidden_messages(
        self,
        session_id: str,
        messages: list[Message],
    ) -> None:
        """Store hidden messages (tool calls/results).

        Delegates to MessageInjector (ТЗ-001 §8).

        Args:
            session_id: Session identifier
            messages: Hidden messages to store
        """
        self._injector.store_hidden_messages(session_id, messages)

    def get_session_fingerprint(self, messages: list[Message]) -> str:
        """Calculate session fingerprint from messages.

        Delegates to SessionManager (ТЗ-001 §8).

        Args:
            messages: Message array

        Returns:
            Fingerprint string
        """
        return self._sessions.calculate_fingerprint(messages)

    async def process_user_message(
        self,
        user_id: str,
        text: str,
        headers: dict[str, str],
    ) -> str:
        """Process single user message through full pipeline.

        Phase 3: Full LLM integration with tool execution loop.
        Implements complete processing: context → LLM → tools → filtering.

        Args:
            user_id: User identifier
            text: User message text
            headers: Request headers

        Returns:
            Filtered response text
        """
        from ....config import get_config
        from ....openai_chat import Message, OpenAIChat

        # Build messages
        messages = [Message(role="user", content=text)]

        # Resolve user context (papik identification + memory)
        user_context = await self.resolve_user_context(user_id, headers)

        # Get session
        session_id = self.get_session_fingerprint(messages)

        # Merge hidden context (tool calls from previous turns)
        messages_with_context = self.merge_hidden_context(messages, session_id)

        # Inject diary context (RAG)
        diary_context = await self.inject_diary_context(messages_with_context)

        # Build system prompt with user context
        system_prompt = self.build_system_prompt(user_context, diary_context)

        # Get upstream endpoint
        config = get_config()
        upstream = config.proxy_upstream if config.proxy_upstream.endpoint.base_url else config.llm
        openai = OpenAIChat(endpoint=upstream)

        # Get tool schemas
        tool_schemas = self._tools.get_tool_schemas()

        # Tool calling loop (Phase 3)
        final_content = ""
        max_iterations = 6

        try:
            for iteration in range(max_iterations):
                logger.debug(f"Tool iteration {iteration + 1}/{max_iterations}")

                # Call LLM
                response = await openai.chat(
                    messages=messages_with_context,
                    system_prompt=system_prompt,
                    tools=tool_schemas,
                )

                if not response.choices:
                    break

                choice_message = response.choices[0].get("message", {})
                content = choice_message.get("content") or ""
                tool_calls = choice_message.get("tool_calls")

                # Log raw LLM response for debugging
                logger.debug(f"LLM response (iteration {iteration + 1}): {content[:200]}...")

                # Append assistant message
                assistant_msg = Message(role="assistant", content=content, tool_calls=tool_calls)
                messages_with_context.append(assistant_msg)

                # If no tool calls, we're done
                if not tool_calls:
                    final_content = content
                    break

                # Execute tool calls
                tool_results = await self._tools.execute_tool_calls(tool_calls, messages_with_context)
                messages_with_context.extend(tool_results)

                # Store hidden context (assistant + tool results)
                self.store_hidden_messages(session_id, [assistant_msg] + tool_results)

        except Exception:
            logger.exception("Error in tool calling loop")
            final_content = "Произошла ошибка при обработке сообщения."
        finally:
            await openai.close()

        # Filter thinking from response (Phase 1)
        filtered = self.filter_response(final_content)

        # CRITICAL DEBUG: Log filtering process
        logger.error(f"[SERVICE] Raw LLM content: {final_content[:300]!r}")
        logger.error(f"[SERVICE] Filtered content: {filtered.content[:300]!r}")
        logger.error(f"[SERVICE] Filter extracted thinking: {filtered.thinking is not None}")
        logger.error(f"[SERVICE] Filter extracted emotion: {filtered.emotion}")

        # Log thinking for debugging (not sent to user)
        if filtered.thinking:
            logger.debug(f"[THINKING] {filtered.thinking}")
        if filtered.emotion:
            logger.debug(f"[EMOTION] {filtered.emotion}")

        # Log raw vs filtered for debugging
        if final_content != filtered.content:
            logger.info(f"Filter applied: raw_len={len(final_content)}, filtered_len={len(filtered.content)}")
            logger.debug(f"Raw content: {final_content[:200]}...")
            logger.debug(f"Filtered content: {filtered.content[:200]}...")

        return filtered.content
