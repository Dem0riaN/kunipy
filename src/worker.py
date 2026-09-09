"""Refactored Worker for clean architecture.

Worker that processes notifications using dependency injection.
Based on ТЗ-001 punkt 5 (clean architecture refactoring).
"""

import asyncio
import json
import logging
import random
from typing import Any

from .character import build_system_prompt
from .config import Config
from .diary import Diary
from .interfaces.worker import INotificationManager
from .notification_manager import Notification
from .openai_chat import Message, OpenAIChat
from .telegram_client import TelegramClient
from .tools import create_default_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6


class Worker:
    """Worker that processes notifications via DI.

    Responsibilities:
    - Pull notifications from queue
    - Run LLM tool-calling loop
    - Maintain per-chat conversation context
    - Manage sleep/wake cycles
    """

    def __init__(
        self,
        name: str,
        openai: OpenAIChat,
        notification_manager: INotificationManager,
        telegram: TelegramClient | None,
        diary: Diary | None,
        config: Config,
        working_memory_context: str | None = None,
    ):
        """Initialize worker with dependencies.

        Args:
            name: Worker identifier
            openai: LLM client
            notification_manager: Notification queue
            telegram: Telegram client (optional)
            diary: Diary for memory (optional)
            config: Application configuration
            working_memory_context: Pre-loaded working memory context (optional)
        """
        self.name = name
        self.openai = openai
        self.notification_manager = notification_manager
        self.telegram = telegram
        self.diary = diary
        self.config = config
        self._working_memory_context = working_memory_context or ""

        self._running = False
        self._sleeping = False
        self._wake_event = asyncio.Event()

        # Per-chat conversation history
        self.temporary_context: dict[int, list[Message]] = {}

    async def run(self) -> None:
        """Main worker loop."""
        self._running = True
        logger.info(f"Worker {self.name} started")

        while self._running:
            try:
                # Get next notification (blocking)
                notification = await self.notification_manager.get()
                if notification is None:
                    break

                # Process notification
                await self._process_notification(notification)

                # Maybe go to sleep after processing
                await self._maybe_sleep()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(f"Worker {self.name} error")
                await asyncio.sleep(1)

        logger.info(f"Worker {self.name} stopped")

    async def _process_notification(self, notification: Notification) -> None:
        """Process a single notification end-to-end."""
        logger.debug(f"Worker {self.name} processing notification")

        # Extract chat_id from pin
        chat_id = None
        if notification.pin and notification.pin.startswith("chat_"):
            try:
                chat_id = int(notification.pin.split("_")[1])
            except (IndexError, ValueError):
                pass

        if chat_id is None:
            logger.warning(f"Notification has invalid pin: {notification.pin}")
            return

        try:
            final_text = await self._generate_response(notification, chat_id)
        except Exception:
            logger.exception(f"Worker {self.name} failed to generate response")
            return

        # Fallback: if LLM produced text but didn't call send_message tool
        if final_text and self.telegram:
            try:
                from .tools import _simulate_typing
                await _simulate_typing(self.telegram, chat_id, final_text)
                await self.telegram.send_message(chat_id, final_text)
                logger.info(f"Worker {self.name} sent fallback response")
            except (ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.error(f"Failed to send fallback message: {e}")

    async def _generate_response(
        self, notification: Notification, chat_id: int
    ) -> str | None:
        """Run LLM tool-calling loop.

        Returns:
            Leftover text if model finished without calling tools, else None
        """
        if not self.openai:
            return None

        chat = await self.telegram.get_chat(chat_id) if self.telegram else None
        is_admin = chat_id == self.config.papik_chat_id

        # Maintain per-chat history
        history = self.temporary_context.setdefault(chat_id, [])
        history.append(Message(role="user", content=notification.message))

        # Build tools
        tools = None
        tool_schemas = None
        if self.telegram:
            recent_bot_messages = [
                m.content for m in history
                if m.role == "assistant" and (m.content or "").strip()
            ]
            tools = create_default_tools(
                telegram=self.telegram,
                diary=self.diary,
                openai=self.openai,
                current_chat=chat,
                is_admin=is_admin,
                recent_bot_messages=recent_bot_messages,
            )
            tool_schemas = tools.to_json_schemas()

        system_prompt = await self._build_system_prompt(notification)
        messages = list(history)
        ever_called_tool = False

        # Tool-calling loop
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await self.openai.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tool_schemas,
                temperature=0.7,
                max_tokens=2000,
            )

            if not response.choices:
                break

            choice = response.choices[0]
            _ = choice.get("finish_reason")  # Used by upstream, not here
            message = choice.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # Log assistant turn
            self._log_assistant_turn(chat_id, content, tool_calls)

            # Add assistant message to history
            history.append(Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls if tool_calls else None
            ))
            messages.append(Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls if tool_calls else None
            ))

            # Execute tools if called
            if tool_calls:
                ever_called_tool = True
                tool_results = []

                for tc in tool_calls:
                    tool_id = tc.get("id")
                    function = tc.get("function", {})
                    name = function.get("name")
                    args_str = function.get("arguments", "{}")

                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        result = await tools.call(name, args)
                        result_str = str(result) if result is not None else ""
                    except (ValueError, KeyError, TypeError, RuntimeError) as e:
                        result_str = f"Error: {e}"
                        logger.error(f"Tool {name} failed: {e}")

                    tool_results.append(Message(
                        role="tool",
                        content=result_str,
                        tool_call_id=tool_id
                    ))

                self._log_tool_results(chat_id, tool_calls, tool_results)

                # Add tool results to history
                history.extend(tool_results)
                messages.extend(tool_results)

                continue  # Next iteration

            # No tool calls - model finished
            break

        # Trim history if too long
        if len(history) > 20:
            history[:] = history[-15:]

        # Return leftover text if no tools were ever called
        if not ever_called_tool and messages and messages[-1].role == "assistant":
            return messages[-1].content or None

        return None

    async def _build_system_prompt(self, notification: Notification) -> str:
        """Build system prompt with working memory context."""
        base_prompt = build_system_prompt(
            config=self.config,
            working_memory_text=self._working_memory_context,
            diary_context=""
        )

        return base_prompt

    async def _maybe_sleep(self) -> None:
        """Sleep after processing if idle."""
        if not self.config.worker_sleep_enabled:
            return

        # Random chance to sleep
        if random.random() < 0.3:
            self._sleeping = True
            self._wake_event.clear()

            logger.debug(f"Worker {self.name} going to sleep")

            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self.config.worker_sleep_timeout
                )
            except TimeoutError:
                pass

            self._sleeping = False
            logger.debug(f"Worker {self.name} woke up")

    def wake_up(self) -> None:
        """Wake up this worker if sleeping."""
        if self._sleeping:
            self._wake_event.set()

    def _log_assistant_turn(
        self, chat_id: int, content: str, tool_calls: list[dict[str, Any]] | None
    ) -> None:
        """Log assistant's thinking and tool calls."""
        prefix = f"[chat_{chat_id}]"
        if content and content.strip():
            logger.info(f"{prefix} ▸ thinking: {content.strip()}")

        for tc in (tool_calls or []):
            fn = tc.get("function", {}) or {}
            name = fn.get("name", "?")
            args_raw = fn.get("arguments", "")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                args_str = json.dumps(args, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                args_str = str(args_raw)
            logger.info(f"{prefix} ⚙ {name}({args_str})")

    def _log_tool_results(
        self,
        chat_id: int,
        tool_calls: list[dict[str, Any]] | None,
        tool_results: list[Message],
    ) -> None:
        """Log tool execution results."""
        prefix = f"[chat_{chat_id}]"
        names_by_id = {
            tc.get("id"): (tc.get("function", {}) or {}).get("name", "?")
            for tc in (tool_calls or [])
        }

        for result in tool_results:
            name = names_by_id.get(result.tool_call_id, "?")
            text = (result.content or "").strip()
            if len(text) > 300:
                text = text[:300] + "…"
            logger.info(f"{prefix} ← {name}: {text}")
