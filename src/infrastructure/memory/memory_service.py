"""Memory service - high-level API for memory system (ТЗ-002).

Hybrid architecture: ChromaDB for vector search (HNSW ANN) + SQLite for
metadata, links, preferences, and tags. Writes go to both stores; reads
use ChromaDB for semantic search and SQLite for structured queries.
"""

import logging
import uuid
from datetime import UTC, datetime

from ...config import Config
from ...domain.memory_models import (
    ConversationMessage,
)
from ...interfaces.llm import IEmbeddingProvider
from ...interfaces.memory import (
    IMemoryStore,
    MemoryKind,
    MemoryPiece,
    MemoryScope,
    WorkingMemoryContext,
)
from .conversation_repository import ConversationRepository
from .memory_link_repository import MemoryLinkRepository
from .memory_repository import MemoryRepository
from .memory_tag_repository import MemoryTagRepository
from .user_chat_repository import ChatRepository, UserRepository
from .user_preference_repository import UserPreferenceRepository
from .working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryService:
    """High-level memory service (ТЗ-002 integration).

    Provides unified API for:
    - Conversation history storage (SQLite)
    - Long-term memory creation and retrieval (ChromaDB + SQLite)
    - Working memory management (in-memory + .md file)
    - Context resolution with multi-level scope retrieval
    """

    def __init__(
        self,
        memory_store: IMemoryStore,
        conversation_repo: ConversationRepository,
        memory_repo: MemoryRepository,
        memory_link_repo: MemoryLinkRepository,
        user_preference_repo: UserPreferenceRepository,
        memory_tag_repo: MemoryTagRepository,
        user_repo: UserRepository,
        chat_repo: ChatRepository,
        working_memory: WorkingMemory,
        embedding_provider: IEmbeddingProvider,
        config: Config,
    ):
        """Initialize memory service.

        Args:
            memory_store: ChromaDB-backed vector store (HNSW ANN search)
            conversation_repo: Conversation history repository (SQLite)
            memory_repo: Long-term memory metadata repository (SQLite)
            memory_link_repo: Memory-to-memory links (SQLite)
            user_preference_repo: Per-user preferences (SQLite)
            memory_tag_repo: Memory tags (SQLite)
            user_repo: User repository
            chat_repo: Chat repository
            working_memory: In-memory working memory (.md persistence)
            embedding_provider: Embedding provider for vector generation
            config: Application configuration
        """
        self.memory_store = memory_store
        self.conversation_repo = conversation_repo
        self.memory_repo = memory_repo
        self.memory_link_repo = memory_link_repo
        self.user_preference_repo = user_preference_repo
        self.memory_tag_repo = memory_tag_repo
        self.user_repo = user_repo
        self.chat_repo = chat_repo
        self.working_memory = working_memory
        self.embedding_provider = embedding_provider
        self.config = config

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for text.

        Convenience wrapper around embedding_provider.

        Args:
            text: Input text

        Returns:
            Embedding vector as list of floats
        """
        result = await self.embedding_provider.embedding(text)
        return result.tolist() if hasattr(result, 'tolist') else list(result)

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

        Also updates user/chat last_seen_at timestamps and working memory
        last_interaction time.

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
            display_name=f"User {user_id}"
        )

        # Ensure chat exists
        chat_type = metadata.get("chat_type", "private")
        await self.chat_repo.get_or_create_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            title=metadata.get("chat_title"),
        )

        # Store message in SQLite
        await self.conversation_repo.store_message(msg)

        # Update working memory last_interaction via in-memory WorkingMemory
        await self.working_memory.update_context(
            user_id=user_id,
            chat_id=chat_id,
            updates={"channel": channel},
        )

        return message_id

    async def create_memory(self, piece: MemoryPiece) -> str:
        """Create memory piece in both ChromaDB (vectors) and SQLite (metadata).

        This is the dual-write that enables hybrid search:
        - ChromaDB: HNSW ANN for semantic similarity
        - SQLite: structured queries, full-text search, links, tags

        Args:
            piece: Memory piece to store (must have embedding set)

        Returns:
            Memory ID
        """
        # 1. ChromaDB first (vector search)
        await self.memory_store.create_memory(piece)

        # 2. SQLite (metadata + links + tags)
        await self.memory_repo.create_memory(piece)

        logger.info(f"Created memory {piece.id}: {piece.kind.value}/{piece.scope.value}")
        return piece.id

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
        """Create memory piece from text (generates embedding automatically).

        Kept for tool/CLI compatibility — runtime memory formation uses
        create_memory() directly with pre-computed embeddings.

        Args:
            content: Memory content
            kind: Memory kind
            scope: Memory scope
            user_id: User ID (required for USER scope)
            chat_id: Chat ID (required for CHAT scope)
            channel: Channel
            confidence: Confidence level (-1 to 1)
            importance: Importance level (0 to 1)
            source_message_ids: Source message IDs

        Returns:
            Memory ID
        """
        embedding = await self.embed_text(content)

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

        return await self.create_memory(piece)

    async def retrieve_context(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        query_text: str,
        max_pieces: int = 10,
    ) -> tuple[WorkingMemoryContext, list[MemoryPiece]]:
        """Retrieve full context for LLM prompt.

        Uses ChromaDB HNSW for multi-level scope retrieval:
        1. CHAT scope — chat-specific memories
        2. USER scope — user-specific + cross-channel linked users
        3. PRIVATE scope — desktop owner only
        4. GLOBAL scope — general knowledge

        Args:
            user_id: User ID
            chat_id: Chat ID
            channel: Channel
            query_text: Query text for semantic search
            max_pieces: Maximum memory pieces to retrieve

        Returns:
            Tuple of (working_memory_context, long_term_memories)
        """
        # 1. Working memory from in-memory/file
        working_ctx = await self.working_memory.get_context(user_id, chat_id)

        # 2. Generate query embedding
        query_embedding = await self.embed_text(query_text)

        # 3. Resolve access scopes
        accessible_scopes = await self._resolve_accessible_scopes(user_id, channel)

        # 4. Resolve linked user IDs for cross-channel (ТЗ-002 §7.4)
        linked_user_ids = self._resolve_linked_user_ids(user_id, channel)

        # 5. Multi-level retrieval through ChromaDB HNSW
        all_memories: list[MemoryPiece] = []

        if MemoryScope.CHAT in accessible_scopes:
            chat_results = await self.memory_store.search_memory(
                query_embedding=query_embedding,
                scope=MemoryScope.CHAT,
                chat_id=chat_id,
                limit=3,
                min_confidence=self.config.memory_min_similarity,
            )
            all_memories.extend(chat_results)

        if MemoryScope.USER in accessible_scopes:
            for linked_uid in linked_user_ids:
                user_results = await self.memory_store.search_memory(
                    query_embedding=query_embedding,
                    scope=MemoryScope.USER,
                    user_id=linked_uid,
                    limit=3,
                    min_confidence=self.config.memory_min_similarity,
                )
                all_memories.extend(user_results)

        if MemoryScope.PRIVATE in accessible_scopes:
            private_results = await self.memory_store.search_memory(
                query_embedding=query_embedding,
                scope=MemoryScope.PRIVATE,
                limit=2,
                min_confidence=self.config.memory_min_similarity,
            )
            all_memories.extend(private_results)

        if MemoryScope.GLOBAL in accessible_scopes:
            global_results = await self.memory_store.search_memory(
                query_embedding=query_embedding,
                scope=MemoryScope.GLOBAL,
                limit=2,
                min_confidence=self.config.memory_min_similarity,
            )
            all_memories.extend(global_results)

        # 6. Deduplicate and rank
        memories = self._deduplicate_and_rank(all_memories, max_pieces)

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
        await self.working_memory.add_promise(user_id, chat_id, promise)
        return f"promise-{uuid.uuid4()}"

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
        plan_dict = {
            "description": plan,
            "due_at": due_at.isoformat() if due_at else None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self.working_memory.add_plan(user_id, chat_id, plan_dict)
        return f"plan-{uuid.uuid4()}"

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
        context = await self.working_memory.get_context(user_id, chat_id)
        context.pending_questions.append(question)
        return f"question-{uuid.uuid4()}"

    async def _resolve_accessible_scopes(
        self, user_id: str, channel: str
    ) -> list[MemoryScope]:
        """Resolve accessible memory scopes for user."""
        scopes = [MemoryScope.GLOBAL, MemoryScope.CHAT, MemoryScope.USER]

        # Desktop owner gets PRIVATE scope
        if self.config.desktop_owner_telegram_id:
            if user_id == self.config.desktop_owner_telegram_id:
                scopes.append(MemoryScope.PRIVATE)

        return scopes

    def _resolve_linked_user_ids(self, user_id: str, channel: str) -> list[str]:
        """Resolve linked user IDs for cross-channel context (ТЗ-002 §5, §6.4)."""
        linked_ids = [user_id]

        if self.config.desktop_owner_telegram_id:
            if channel == "desktop" and user_id.startswith("desktop:"):
                linked_ids.append(self.config.desktop_owner_telegram_id)
            elif user_id == self.config.desktop_owner_telegram_id:
                linked_ids.append(f"desktop:{self.config.desktop_owner_telegram_id}")

        return linked_ids

    @staticmethod
    def _deduplicate_and_rank(
        memories: list[MemoryPiece], max_pieces: int
    ) -> list[MemoryPiece]:
        """Deduplicate by ID and rank by importance * confidence."""
        seen_ids: set[str] = set()
        unique: list[MemoryPiece] = []
        for piece in memories:
            if piece.id not in seen_ids:
                seen_ids.add(piece.id)
                unique.append(piece)

        # Sort by importance * confidence (higher = better)
        unique.sort(key=lambda p: p.importance * max(p.confidence, 0), reverse=True)
        return unique[:max_pieces]
