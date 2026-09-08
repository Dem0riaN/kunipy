"""Worker for kunipy.

A worker pulls notifications from the queue and processes them using the LLM,
running a full tool-calling loop (the model can call Telegram/diary/media
tools, see the results, and call more tools, until it stops calling tools).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional

from .character import build_system_prompt
from .config import get_config
from .diary import Diary
from .notification_manager import Notification, NotificationManager
from .openai_chat import Message, OpenAIChat
from .telegram_client import TelegramClient
from .tools import create_default_tools
from .working_memory import get_working_memory

logger = logging.getLogger(__name__)

# Safety cap on how many times the model may chain tool calls for a single
# incoming notification before we give up and just report what happened.
MAX_TOOL_ITERATIONS = 6


class Worker:
    """A worker that processes notifications and generates responses."""

    def __init__(
        self,
        name: str,
        app_base: Any,  # App instance (for callbacks)
        telegram: Optional[TelegramClient],
        openai: Optional[OpenAIChat],
        diary: Optional[Diary],
        notification_manager: NotificationManager,
    ):
        self.name = name
        self.app = app_base
        self.telegram = telegram
        self.openai = openai
        self.diary = diary
        self.notification_manager = notification_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Per-chat short-term conversation history so that unrelated chats
        # don't bleed into each other's context.
        self.temporary_context: Dict[int, List[Message]] = {}
        self._sleeping = False
        self._wake_event = asyncio.Event()
        self.config = get_config()

    async def run(self) -> None:
        """Main worker loop."""
        self._running = True
        logger.info(f"Worker {self.name} started")

        while self._running:
            try:
                # Get next notification (blocking)
                notification = await self.notification_manager.get()
                if notification is None:
                    # Manager stopped
                    break

                # Process the notification
                await self._process_notification(notification)

                # After processing, optionally go to sleep (idle)
                await self._maybe_sleep()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Worker {self.name} error: {e}")
                await asyncio.sleep(1)  # backoff

        logger.info(f"Worker {self.name} stopped")

    async def _process_notification(self, notification: Notification) -> None:
        """Process a single notification end-to-end."""
        logger.debug(f"Worker {self.name} processing {notification._id}")

        # Extract chat_id from pin
        chat_id = None
        if notification.pin.startswith("chat_"):
            try:
                chat_id = int(notification.pin.split("_")[1])
            except (IndexError, ValueError):
                pass

        if chat_id is None:
            logger.warning(f"Notification {notification._id} has invalid pin, skipping")
            return

        try:
            final_text = await self._generate_response(notification, chat_id)
        except Exception as e:
            logger.exception(f"Worker {self.name} failed generating a response: {e}")
            return

        # The LLM is expected to actually deliver its reply by calling the
        # `send_telegram_message` tool during the loop below. If it finished
        # without calling any tool at all but still produced text, treat that
        # text as a plain reply so nothing is silently lost.
        if final_text and self.telegram:
            try:
                from .tools import _simulate_typing
                await _simulate_typing(self.telegram, chat_id, final_text)
                await self.telegram.send_message(chat_id, final_text)
                logger.info(f"Worker {self.name} sent fallback response to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    def _log_assistant_turn(self, chat_id: int, content: str, tool_calls: Optional[List[Dict[str, Any]]]) -> None:
        """Print the model's reasoning text and any tool calls it's about to
        make, so what the bot is "thinking" and doing is visible in the
        console/log instead of only the final delivered message."""
        prefix = f"[chat_{chat_id}]"
        if content and content.strip():
            logger.info(f"{prefix} \u25b8 thinking: {content.strip()}")
        for tc in (tool_calls or []):
            fn = tc.get("function", {}) or {}
            name = fn.get("name", "?")
            args_raw = fn.get("arguments", "")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                args_str = json.dumps(args, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                args_str = str(args_raw)
            logger.info(f"{prefix} \u2699 {name}({args_str})")

    def _log_tool_results(
        self,
        chat_id: int,
        tool_calls: Optional[List[Dict[str, Any]]],
        tool_results: List[Message],
    ) -> None:
        """Print each tool's result next to the call that produced it."""
        prefix = f"[chat_{chat_id}]"
        names_by_id = {tc.get("id"): (tc.get("function", {}) or {}).get("name", "?") for tc in (tool_calls or [])}
        for result in tool_results:
            name = names_by_id.get(result.tool_call_id, "?")
            text = (result.content or "").strip()
            if len(text) > 300:
                text = text[:300] + "\u2026"
            logger.info(f"{prefix} \u2190 {name}: {text}")

    async def _generate_response(self, notification: Notification, chat_id: int) -> Optional[str]:
        """Run the LLM tool-calling loop for one notification.

        Returns leftover assistant text if the model finished without ever
        calling a tool (fallback plain reply), otherwise None (the reply was
        already delivered via the send_telegram_message tool).
        """
        if not self.openai:
            logger.warning("No OpenAI client, skipping response generation")
            return None

        chat = await self.telegram.get_chat(chat_id) if self.telegram else None
        is_admin = chat_id == self.config.papik_chat_id

        history = self.temporary_context.setdefault(chat_id, [])
        history.append(Message(role="user", content=notification.message))

        tools = None
        tool_schemas = None
        if self.telegram:
            recent_bot_messages = [
                m.content for m in history if m.role == "assistant" and (m.content or "").strip()
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

        for _ in range(MAX_TOOL_ITERATIONS):
            from .metrics import breadcrumbs
            with breadcrumbs(chat=f"chat_{chat_id}", function="worker.generate_response"):
                response = await self.openai.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tool_schemas,
                )
            if not response.choices:
                break

            choice_message = response.choices[0].get("message", {})
            content = choice_message.get("content") or ""
            tool_calls = choice_message.get("tool_calls") or None

            self._log_assistant_turn(chat_id, content, tool_calls)

            messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

            if not tool_calls:
                # Model is done. Persist history and hand back any leftover
                # text as a fallback plain reply.
                await self._finish_turn(chat_id, messages)
                return content.strip() if (content and not ever_called_tool) else None

            ever_called_tool = True
            if tools is not None:
                tool_results = await tools.handle_tool_calls(tool_calls, messages)
                self._log_tool_results(chat_id, tool_calls, tool_results)
                messages.extend(tool_results)
            else:
                # No telegram/tool support available; can't fulfil the call.
                for tc in tool_calls:
                    messages.append(Message(
                        role="tool",
                        content="Error: tools are unavailable right now.",
                        tool_call_id=tc.get("id"),
                    ))

        logger.warning(f"Worker {self.name} hit MAX_TOOL_ITERATIONS for chat {chat_id}")
        await self._finish_turn(chat_id, messages)
        return None

    async def _finish_turn(self, chat_id: int, messages: List[Message]) -> None:
        """Persist the chat's short-term history, dumping it to the diary and
        starting fresh once it gets too large (mirrors the original kuni's
        `DIARY_TOKEN_COUNT_TRIGGER` context-reset behavior)."""
        # Rough token estimate (~4 chars/token); good enough for a soft cap,
        # avoids pulling in a real tokenizer just for this check.
        approx_tokens = sum(len(m.content or "") for m in messages) // 4

        if approx_tokens >= self.config.diary_token_count_trigger and hasattr(self.app, "diary_dump_messages"):
            logger.info(
                f"Worker {self.name}: chat {chat_id} reached ~{approx_tokens} tokens, "
                f"dumping context to diary and starting fresh"
            )
            try:
                await self.app.diary_dump_messages(messages)
            except Exception as e:
                logger.error(f"Failed to dump context to diary: {e}")
            self.temporary_context[chat_id] = []
        else:
            self.temporary_context[chat_id] = self._trim_history(messages)

    def _trim_history(self, messages: List[Message]) -> List[Message]:
        """Keep the most recent messages whose combined content length fits
        under `config.chat_max_history_length` characters (0 = unlimited)."""
        limit = self.config.chat_max_history_length
        if not limit:
            return messages

        kept: List[Message] = []
        total = 0
        for m in reversed(messages):
            length = len(m.content or "")
            if kept and total + length > limit:
                break
            kept.append(m)
            total += length
        kept.reverse()
        return kept

    async def _build_system_prompt(self, notification: Notification) -> str:
        """Build the full system prompt: persona + working memory + diary recall."""
        working_memory_text = ""
        wm = get_working_memory()
        stored = wm.get("things_to_remember")
        if stored:
            working_memory_text = str(stored)

        diary_context = ""
        if self.diary and self.openai and notification.message:
            try:
                query_vector = await self.openai.embedding(notification.message)
                related = await self.diary.query(query_vector, max_entries=5)
                if related:
                    diary_context = "\n".join(f"- {entry.body.strip()}" for entry, _score in related if entry.body.strip())
                    max_len = self.config.diary_injection_max_length
                    if max_len and len(diary_context) > max_len:
                        diary_context = diary_context[:max_len].rsplit("\n", 1)[0] + "\n- [...]"
            except Exception as e:
                logger.warning(f"Failed to fetch related diary entries: {e}")

        prompt = build_system_prompt(
            self.config,
            working_memory_text=working_memory_text,
            diary_context=diary_context,
        )

        # Occasionally nudge the model to remember it must call
        # `send_telegram_message` to actually deliver its reply -- plain
        # text finishing without any tool call is silently treated as a
        # fallback and easy for smaller models to "forget" over a long chat.
        if random.random() < self.config.tool_reminder_probability:
            prompt += (
                "\n\n# Reminder\nRemember to actually call `send_telegram_message` "
                "to send your reply -- text you return without calling a tool is "
                "never shown to the user."
            )

        return prompt

    async def _maybe_sleep(self) -> None:
        """Randomly go to sleep if configured."""
        if not self.config.randomly_go_sleep:
            return
        # Sleep with low probability (e.g., 5% chance after each notification)
        if random.random() < 0.05:
            sleep_time = random.randint(10, 60)  # seconds
            logger.info(f"Worker {self.name} sleeping for {sleep_time}s")
            self._sleeping = True
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                pass
            self._sleeping = False

    def wake_up(self) -> None:
        """Wake up the worker if sleeping."""
        if self._sleeping:
            logger.info(f"Waking up worker {self.name}")
            self._wake_event.set()
            # We can't easily interrupt asyncio.sleep, so we rely on the loop to check.

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
