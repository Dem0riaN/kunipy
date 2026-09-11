"""Memory service - high-level API for memory system (ТЗ-002)."""

import logging
import uuid
from datetime import UTC, datetime

from ...config import Config
from ...domain.memory_models import (
    ConversationMessage,
    RetrievalContext,
    WorkingMemoryItem,
)
from ...interfaces.llm import IEmbeddingProvider
from ...interfaces.memory import (
    MemoryKind,
    MemoryPiece,
    MemoryScope,
    WorkingMemoryContext,
)
from .conversation_repository import ConversationRepository
from .memory_repository import MemoryRepository
from .user_chat_repository import ChatRepository, UserRepository
from .working_memory_repository import WorkingMemoryRepository

logger = logging.getLogger(__name__)


class MemoryService:
    """High-level memory service (ТЗ-002 integration).

    Provides unified API for:
    - Conversation history storage
    - Long-term memory creation and retrieval
    - Working memory management
    - Context resolution
    """

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        memory_repo: MemoryRepository,
        working_memory_repo: WorkingMemoryRepository,
        user_repo: UserRepository,
        chat_repo: ChatRepository,
        embedding_provider: IEmbeddingProvider,
        config: Config,
    ):
        """Initialize memory service.

        Args:
            conversation_repo: Conversation history repository
            memory_repo: Long-term memory repository
            working_memory_repo: Working memory repository
            user_repo: User repository
            chat_repo: Chat repository
            embedding_provider: Embedding provider for vector generation
            config: Application configuration
        """
        self.conversation_repo = conversation_repo
        self.memory_repo = memory_repo
        self.working_memory_repo = working_memory_repo
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.embedding_provider = embedding_provider
        self.config = config

    async def store_message(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        role: str,
        content: str,
        message_id: str | None = None,
        reply_to_message_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Store message in conversation history.

        Also updates user/chat last_seen_at timestamps.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel (telegram, desktop, voice)
            role: Message role (user, assistant, system)
            content: Message content
            message_id: Optional message ID (generated if not provided)
            reply_to_message_id: Optional reply-to message ID
            metadata: Optional metadata dict

        Returns:
            Message ID
        """
        if message_id is None:
            message_id = str(uuid.uuid4())

        if metadata is None:
            metadata = {}

        msg = ConversationMessage(
            message_id=message_id,
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            timestamp=datetime.now(UTC),
            role=role,
            content=content,
            reply_to_message_id=reply_to_message_id,
            metadata=metadata,
        )

        # Ensure user exists
        await self.user_repo.get_or_create_user(
            user_id=user_id,
            display_name=f"User {user_id}"  # Default name, should be updated
        )

        # Ensure chat exists
        chat_type = metadata.get("chat_type", "private")

        await self.chat_repo.get_or_create_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            title=metadata.get("chat_title"),
        )

        # Store message
        await self.conversation_repo.store_message(msg)

        # Update working memory last_interaction
        await self.working_memory_repo.update_context(
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            updates={},  # Just update timestamp
        )

        return message_id

    async def create_memory_from_text(
        self,
        content: str,
        kind: MemoryKind,
        scope: MemoryScope,
        user_id: str | None,
        chat_id: str | None,
        channel: str | None,
        confidence: float = 0.0,
        importance: float = 0.5,
        source_message_ids: list[str] | None = None,
    ) -> str:
        """Create memory piece from text.

        Args:
            content: Memory content
            kind: Memory kind (entity_description, thought, event, fact, other)
            scope: Memory scope (private, user, chat, shared, global)
            user_id: User ID (required for USER scope)
            chat_id: Chat ID (required for CHAT scope)
            channel: Channel (telegram, desktop, voice)
            confidence: Confidence level (-1 to 1)
            importance: Importance level (0 to 1)
            source_message_ids: Source message IDs

        Returns:
            Memory ID
        """
        # Generate embedding
        embedding_result = await self.embedding_provider.embedding(content)
        embedding = embedding_result.tolist() if hasattr(embedding_result, 'tolist') else list(embedding_result)

        # Create memory piece
        piece = MemoryPiece(
            id=str(uuid.uuid4()),
            kind=kind,
            content=content,
            confidence=confidence,
            importance=importance,
            scope=scope,
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            embedding=embedding,
            source_type="conversation",
            source_message_ids=source_message_ids or [],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_used=datetime.now(UTC),
            usage_count=0,
        )

        memory_id = await self.memory_repo.create_memory(piece)
        logger.info(f"Created memory {memory_id}: {kind.value}/{scope.value}")
        return memory_id

    async def retrieve_context(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        query_text: str,
        max_pieces: int = 10,
    ) -> tuple[WorkingMemoryContext, list[MemoryPiece]]:
        """Retrieve full context for LLM prompt.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            query_text: Query text for semantic search
            max_pieces: Maximum memory pieces to retrieve

        Returns:
            Tuple of (working_memory_context, long_term_memories)
        """
        # Get working memory
        working_ctx = await self.working_memory_repo.get_context(
            user_id, chat_id, channel
        )

        # Generate query embedding
        query_embedding_result = await self.embedding_provider.embedding(query_text)
        query_embedding = query_embedding_result.tolist() if hasattr(query_embedding_result, 'tolist') else list(query_embedding_result)

        # Resolve access scopes
        accessible_scopes = await self._resolve_accessible_scopes(
            user_id, channel
        )

        # Multi-level retrieval
        memories = await self._retrieve_memories(
            query_embedding=query_embedding,
            user_id=user_id,
            chat_id=chat_id,
            accessible_scopes=accessible_scopes,
            max_pieces=max_pieces,
        )

        # Update usage statistics
        for memory in memories:
            memory.last_used = datetime.now(UTC)
            memory.usage_count += 1
            await self.memory_repo.update_memory(memory)

        return working_ctx, memories

    async def add_promise(
        self, user_id: str, chat_id: str, channel: str, promise: str
    ) -> str:
        """Add promise to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            promise: Promise text

        Returns:
            Promise item ID
        """
        item = WorkingMemoryItem(
            id=str(uuid.uuid4()),
            item_type="promise",
            content=promise,
        )
        return await self.working_memory_repo.add_item(
            user_id, chat_id, channel, item
        )

    async def add_plan(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        plan: str,
        due_at: datetime | None = None,
    ) -> str:
        """Add plan to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            plan: Plan text
            due_at: Due date (optional)

        Returns:
            Plan item ID
        """
        item = WorkingMemoryItem(
            id=str(uuid.uuid4()),
            item_type="plan",
            content=plan,
            due_at=due_at,
        )
        return await self.working_memory_repo.add_item(
            user_id, chat_id, channel, item
        )

    async def add_question(
        self, user_id: str, chat_id: str, channel: str, question: str
    ) -> str:
        """Add pending question to working memory.

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            question: Question text

        Returns:
            Question item ID
        """
        item = WorkingMemoryItem(
            id=str(uuid.uuid4()),
            item_type="question",
            content=question,
        )
        return await self.working_memory_repo.add_item(
            user_id, chat_id, channel, item
        )

    async def _resolve_accessible_scopes(
        self, user_id: str, channel: str
    ) -> list[MemoryScope]:
        """Resolve accessible memory scopes for user.

        Args:
            user_id: User ID
            channel: Channel

        Returns:
            List of accessible scopes
        """
        scopes = [MemoryScope.GLOBAL]  # Always accessible

        # Add CHAT and USER scopes
        scopes.append(MemoryScope.CHAT)
        scopes.append(MemoryScope.USER)

        # Check if desktop owner (access to PRIVATE scope)
        if self.config.desktop_owner_telegram_id:
            if user_id == self.config.desktop_owner_telegram_id:
                scopes.append(MemoryScope.PRIVATE)

        return scopes

    async def _retrieve_memories(
        self,
        query_embedding: list[float],
        user_id: str,
        chat_id: str,
        accessible_scopes: list[MemoryScope],
        max_pieces: int,
    ) -> list[MemoryPiece]:
        """Multi-level memory retrieval.

        Args:
            query_embedding: Query embedding vector
            user_id: User ID
            chat_id: Chat ID
            accessible_scopes: Accessible scopes
            max_pieces: Maximum pieces to return

        Returns:
            Ranked list of memory pieces
        """
        all_results = []

        # 1. Chat-specific memories
        if MemoryScope.CHAT in accessible_scopes:
            chat_results = await self.memory_repo.search_by_embedding(
                query_embedding=query_embedding,
                scope=MemoryScope.CHAT,
                chat_id=chat_id,
                limit=3,
                min_confidence=self.config.memory_min_similarity,
            )
            all_results.extend(chat_results)

        # 2. User-specific memories
        if MemoryScope.USER in accessible_scopes:
            user_results = await self.memory_repo.search_by_embedding(
                query_embedding=query_embedding,
                scope=MemoryScope.USER,
                user_id=user_id,
                limit=3,
                min_confidence=self.config.memory_min_similarity,
            )
            all_results.extend(user_results)

        # 3. Private memories (for desktop owner)
        if MemoryScope.PRIVATE in accessible_scopes:
            private_results = await self.memory_repo.search_by_embedding(
                query_embedding=query_embedding,
                scope=MemoryScope.PRIVATE,
                limit=2,
                min_confidence=self.config.memory_min_similarity,
            )
            all_results.extend(private_results)

        # 4. Global memories
        if MemoryScope.GLOBAL in accessible_scopes:
            global_results = await self.memory_repo.search_by_embedding(
                query_embedding=query_embedding,
                scope=MemoryScope.GLOBAL,
                limit=2,
                min_confidence=self.config.memory_min_similarity,
            )
            all_results.extend(global_results)

        # Deduplicate by ID
        seen_ids = set()
        deduplicated = []
        for piece, score in all_results:
            if piece.id not in seen_ids:
                seen_ids.add(piece.id)
                deduplicated.append((piece, score))

        # Sort by final score
        sorted_results = sorted(deduplicated, key=lambda x: x[1], reverse=True)

        # Return top pieces
        return [piece for piece, score in sorted_results[:max_pieces]]
