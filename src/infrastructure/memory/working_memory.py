"""Working memory implementation (ТЗ-002 punkt 7.6)."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ...interfaces.memory import IWorkingMemory, WorkingMemoryContext

if TYPE_CHECKING:
    from .working_memory_file_store import WorkingMemoryFileStore

logger = logging.getLogger(__name__)


class WorkingMemory(IWorkingMemory):
    """In-memory working memory for current interaction state.

    Phase 3: Optional file persistence via WorkingMemoryFileStore.
    When file_store is configured, save_to_file() writes all contexts to disk
    so state survives application restarts.
    """

    def __init__(
        self,
        file_store: "WorkingMemoryFileStore | None" = None,
    ):
        """Initialize working memory store.

        Args:
            file_store: Optional file persistence handler
        """
        self._contexts: dict[tuple[str, str], WorkingMemoryContext] = {}
        self._file_store = file_store

        # Load from file if available
        if file_store:
            try:
                loaded = file_store.load_contexts()
                for ctx in loaded:
                    key = (ctx.user_id, ctx.chat_id)
                    self._contexts[key] = ctx
                if loaded:
                    logger.info(f"Loaded {len(loaded)} working memory contexts from file")
            except Exception as e:
                logger.warning(f"Failed to load working memory from file: {e}")

        logger.info("Initialized WorkingMemory")

    async def get_context(
        self,
        user_id: str,
        chat_id: str
    ) -> WorkingMemoryContext:
        """Get current working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID

        Returns:
            Current context (creates empty if doesn't exist)
        """
        key = (user_id, chat_id)
        if key not in self._contexts:
            self._contexts[key] = WorkingMemoryContext(
                user_id=user_id,
                chat_id=chat_id,
                channel="telegram",
                last_interaction=datetime.now(UTC)
            )
            logger.debug(f"Created new context for user={user_id}, chat={chat_id}")
        else:
            self._contexts[key].last_interaction = datetime.now(UTC)

        return self._contexts[key]

    async def update_context(
        self,
        user_id: str,
        chat_id: str,
        updates: dict[str, Any]
    ) -> None:
        """Update working memory context.

        Args:
            user_id: User ID
            chat_id: Chat ID
            updates: Fields to update
        """
        context = await self.get_context(user_id, chat_id)

        for key, value in updates.items():
            if hasattr(context, key):
                setattr(context, key, value)
            else:
                context.metadata[key] = value

        logger.debug(f"Updated context for user={user_id}, chat={chat_id}: {list(updates.keys())}")

    async def add_promise(
        self,
        user_id: str,
        chat_id: str,
        promise: str
    ) -> None:
        """Add promise to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            promise: Promise description
        """
        context = await self.get_context(user_id, chat_id)
        context.promises.append({
            "description": promise,
            "created_at": datetime.now(UTC).isoformat(),
            "fulfilled": False
        })
        logger.debug(f"Added promise for user={user_id}, chat={chat_id}: {promise}")

    async def add_plan(
        self,
        user_id: str,
        chat_id: str,
        plan: dict[str, Any]
    ) -> None:
        """Add plan to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            plan: Plan details
        """
        context = await self.get_context(user_id, chat_id)
        context.plans.append(plan)
        logger.debug(f"Added plan for user={user_id}, chat={chat_id}")

    async def clear_context(
        self,
        user_id: str,
        chat_id: str
    ) -> None:
        """Clear working memory for context.

        Args:
            user_id: User ID
            chat_id: Chat ID
        """
        key = (user_id, chat_id)
        if key in self._contexts:
            del self._contexts[key]
            logger.debug(f"Cleared context for user={user_id}, chat={chat_id}")

    def save_to_file(self) -> None:
        """Persist working memory to disk via WorkingMemoryFileStore.

        Phase 3: Delegates to file_store.save_all() when configured.
        No-op when file_store is not set.
        """
        if self._file_store:
            try:
                self._file_store.save_all(self._contexts)
                logger.debug(f"Saved {len(self._contexts)} working memory contexts to file")
            except Exception as e:
                logger.error(f"Failed to save working memory to file: {e}")
        else:
            logger.debug("save_to_file called but no file_store configured")

    @property
    def contexts(self) -> dict[tuple[str, str], WorkingMemoryContext]:
        """Access raw contexts dict (read-only intent)."""
        return self._contexts
