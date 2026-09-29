"""User context management for proxy.

Manages user identification, papik context, and cross-channel memory.
Following ТЗ-001 §32 - Character context management.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ....character import build_system_prompt
from .models import UserContext

if TYPE_CHECKING:
    from ...config import Config
    from ...infrastructure.memory.working_memory_file_store import WorkingMemoryFileStore

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages user context and papik identification.

    Responsibilities (ТЗ-001 §32):
    - Resolve user context from headers
    - Papik identification logic
    - Cross-channel memory linking (ТЗ-001 §23)
    - System prompt personalization

    Architecture: Service layer coordinating memory access (ТЗ-001 §8)
    """

    def __init__(
        self,
        config: Config,
        wm_store: WorkingMemoryFileStore | None = None,
    ):
        """Initialize context manager.

        Args:
            config: Application config (ТЗ-001 §57)
            wm_store: Working memory file store OR WorkingMemory instance (injected dependency, ТЗ-001 §8)
        """
        self._config = config
        self._wm_store = wm_store
        logger.info("ContextManager initialized")

    async def resolve_user_context(
        self,
        user_id: str,
        headers: dict[str, str],
    ) -> UserContext:
        """Resolve user context from user_id and headers.

        Identification logic:
        1. Check X-Papik-Auth: true header
        2. Check X-Telegram-ID matches papik_chat_id
        3. Default: treat all proxy users as papik (single-user mode)

        Cross-channel memory (ТЗ-001 §23):
        - Loads memory for linked user IDs
        - Telegram ID → Proxy ID mapping
        - Seamless continuity between channels

        Args:
            user_id: User identifier
            headers: Request headers

        Returns:
            UserContext with identification and memory
        """
        is_papik = False
        telegram_id = None

        # 1. Check explicit papik auth
        if headers.get("X-Papik-Auth") == "true":
            is_papik = True
            logger.info(f"User {user_id} identified as papik via X-Papik-Auth header")

        # 2. Check telegram ID match
        if headers.get("X-Telegram-ID"):
            telegram_id = headers["X-Telegram-ID"]
            if telegram_id == str(self._config.papik_chat_id):
                is_papik = True
                logger.info(f"User {user_id} identified as papik via Telegram ID {telegram_id}")

        # 3. Default: treat all proxy users as papik (single-user mode for Open-LLM-VTuber)
        if not telegram_id and getattr(self._config, "proxy_default_user_as_papik", True):
            is_papik = True
            telegram_id = str(self._config.papik_chat_id)
            logger.info(f"User {user_id} treated as papik (single-user mode)")

        # 4. Resolve linked user IDs
        linked_ids = self._resolve_linked_user_ids(telegram_id) if telegram_id else []

        # 5. Load working memory
        wm_text = self._get_working_memory_for_user(linked_ids)

        return UserContext(
            user_id=user_id,
            is_papik=is_papik,
            telegram_id=telegram_id,
            linked_user_ids=linked_ids,
            working_memory=wm_text,
            display_name=self._config.papik_name if is_papik else user_id,
        )

    def build_system_prompt(
        self,
        context: UserContext,
        diary_context: str = "",
    ) -> str:
        """Build system prompt with user context.

        Integrates (ТЗ-001 §32):
        - Character personality
        - Working memory
        - Diary RAG context
        - Papik identification

        Args:
            context: User context
            diary_context: Diary RAG context

        Returns:
            Complete system prompt
        """
        # Check if proxy mode should use different prompt
        # Use config.proxy_mode setting instead of file existence check
        use_proxy_mode = getattr(self._config, "proxy_mode", "direct") == "direct"

        if use_proxy_mode:
            # Use specialized proxy mode prompt instead of full Telegram system prompt
            from ....character import load_character_prompt
            from ....prompt_loader import load_prompt

            # Load proxy mode instructions
            proxy_instructions = load_prompt("proxy_mode", "prompts", config=self._config)

            # Load character persona (same as Telegram mode)
            character_persona = load_character_prompt(self._config, ".")

            # Build simplified system prompt for proxy mode
            parts = [proxy_instructions, character_persona]

            if context.working_memory:
                parts.append(f"\n<things_to_remember>\n{context.working_memory}\n</things_to_remember>")

            if diary_context:
                parts.append(f"\n<related_memories>\n{diary_context}\n</related_memories>")

            base_prompt = "\n\n".join(parts)
        else:
            # Standard Telegram mode prompt
            base_prompt = build_system_prompt(
                self._config,
                working_memory_text=context.working_memory,
                diary_context=diary_context,
            )

        # Add papik-specific context
        if context.is_papik and not use_proxy_mode:
            # Only add this context in Telegram mode
            papik_context = f"""

# User Context
You are talking to {context.display_name} (your owner/papik).
This conversation is happening through Open-LLM-VTuber proxy (NOT Telegram).

IMPORTANT CONTEXT:
- This is a text-only interface (no Telegram functions like #wait, #ask, #search, etc.)
- You cannot call Telegram tools here - they don't exist in this interface
- Just respond naturally in text - your message will be spoken aloud by the VTuber
- Your memory is shared across Telegram and this proxy - seamless continuity
- The user experiences you as a speaking VTuber character, not a text chatbot
"""
            base_prompt += papik_context

        # Add structured output format instructions (for ThinkingFilter)
        thinking_mode = getattr(self._config, "proxy_thinking_filter_mode", "structured")
        if thinking_mode == "structured":
            base_prompt += """

# ⚠️ CRITICAL OUTPUT FORMAT - MANDATORY ⚠️

YOU MUST ALWAYS RESPOND WITH THIS EXACT JSON STRUCTURE. NO EXCEPTIONS.

Return ONLY a raw JSON object (no markdown, no code blocks, no extra text):

{"thinking": "your internal analysis here", "emotion": "happy", "response": "your message to user"}

RULES:
1. NO markdown code blocks (no ``` or ```json)
2. NO text before or after the JSON
3. "thinking" = your internal thoughts (user NEVER sees this)
4. "response" = what the user reads/hears (MUST NOT be empty)
5. "emotion" = one word only (happy/sad/curious/smirk/etc)
6. DO NOT put emotion tags like [happy] or [smirk] in "response"

CORRECT EXAMPLES:

Input: "Привет!"
Output: {"thinking": "User greeted me warmly", "emotion": "happy", "response": "Привет! Как дела?"}

Input: "Помнишь пароль?"
Output: {"thinking": "User asking about password I stored", "emotion": "smirk", "response": "Конечно помню - это был 'виноград', верно?"}

WRONG EXAMPLES (DO NOT DO THIS):

❌ ```json\n{"thinking":"...", "response":"..."}\n```  (markdown blocks forbidden)
❌ {"thinking": "User greeted", "response": "[happy] Привет!"}  (emotion tags forbidden in response)
❌ {"thinking": "User greeted me warmly...", "response": ""}  (empty response forbidden)
❌ [smirk] Помню конечно  (plain text with emotion tags - must be JSON)

REMEMBER: The user only sees "response" field. Everything else is hidden from them.
"""

        return base_prompt

    def _resolve_linked_user_ids(self, telegram_id: str) -> list[str]:
        """Resolve linked user IDs for cross-channel memory.

        Returns list of user IDs to search in:
        - Telegram chat ID
        - Desktop user ID (if configured)
        - Proxy user ID

        Ensures seamless memory across:
        - Telegram conversations
        - Proxy conversations (Open-LLM-VTuber)
        - Desktop interactions (future)

        Args:
            telegram_id: Telegram user ID

        Returns:
            List of linked user IDs
        """
        linked = [telegram_id]

        if hasattr(self._config, "desktop_owner_telegram_id") and self._config.desktop_owner_telegram_id:
            linked.append(self._config.desktop_owner_telegram_id)

        # Add proxy-specific user ID
        linked.append(f"proxy_{telegram_id}")

        logger.debug(f"Resolved linked user IDs: {linked}")
        return linked

    def _get_working_memory_for_user(self, user_ids: list[str]) -> str:
        """Load working memory for all linked user IDs.

        Memory Integration (ТЗ-001 §22 - Memory Independence):
        Handles both WorkingMemoryFileStore and WorkingMemory instances.

        Args:
            user_ids: List of user IDs to load memory for

        Returns:
            Combined working memory text
        """
        if not self._wm_store or not user_ids:
            return ""

        try:
            # Check if wm_store has load_all method (WorkingMemoryFileStore)
            if hasattr(self._wm_store, "load_all"):
                # WorkingMemoryFileStore.load_all() returns dict[(user_id, chat_id), data]
                all_data = self._wm_store.load_all()
                texts = []

                for uid in user_ids:
                    # Try to find matching entries by user_id (first element of tuple key)
                    for (user_id, chat_id), data in all_data.items():
                        if user_id == uid:
                            # Format memory text from context data
                            memory_parts = []

                            if data.get("current_topic"):
                                memory_parts.append(f"Topic: {data['current_topic']}")

                            if data.get("conversation_summary"):
                                memory_parts.append(f"Summary: {data['conversation_summary']}")

                            if data.get("promises"):
                                promises_text = ", ".join([
                                    p.get("description", str(p)) if isinstance(p, dict) else str(p)
                                    for p in data["promises"]
                                ])
                                memory_parts.append(f"Promises: {promises_text}")

                            if data.get("pending_questions"):
                                questions_text = ", ".join(data["pending_questions"])
                                memory_parts.append(f"Questions: {questions_text}")

                            if memory_parts:
                                memory_text = "; ".join(memory_parts)
                                texts.append(f"## Working Memory - {uid}\n{memory_text}")
                            break

                result = "\n\n".join(texts)
                if result:
                    logger.info(f"Loaded working memory for {len(texts)} user IDs ({len(result)} chars)")
                return result

            # Check if wm_store is WorkingMemory instance with _contexts attribute
            elif hasattr(self._wm_store, "_contexts"):
                # WorkingMemory instance - access internal _contexts directly (sync)
                contexts_dict = self._wm_store._contexts
                file_store = getattr(self._wm_store, "_file_store", None)

                texts = []
                for uid in user_ids:
                    # Try to find matching entries by user_id (first element of tuple key)
                    for (user_id, chat_id), ctx in contexts_dict.items():
                        if user_id == uid:
                            # Use file_store.render_for_prompt if available
                            if file_store and hasattr(file_store, "render_for_prompt"):
                                rendered = file_store.render_for_prompt(ctx)
                                if rendered:
                                    texts.append(f"## Working Memory - {uid}\n{rendered}")
                            else:
                                # Fallback: format context manually
                                memory_parts = []
                                if hasattr(ctx, "current_topic") and ctx.current_topic:
                                    memory_parts.append(f"Topic: {ctx.current_topic}")
                                if hasattr(ctx, "conversation_summary") and ctx.conversation_summary:
                                    memory_parts.append(f"Summary: {ctx.conversation_summary}")
                                if memory_parts:
                                    memory_text = "; ".join(memory_parts)
                                    texts.append(f"## Working Memory - {uid}\n{memory_text}")
                            break

                result = "\n\n".join(texts)
                if result:
                    logger.info(f"Loaded working memory for {len(texts)} user IDs ({len(result)} chars)")
                return result

            else:
                logger.warning(f"Unknown working memory store type: {type(self._wm_store)}")
                return ""

        except Exception as e:
            logger.error(f"Failed to load working memory: {e}")
            return ""
