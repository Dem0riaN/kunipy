# Проектирование новой системы памяти (ТЗ-002 Этап 2)

## Дата: 2026-09-11

## 1. Database Schema (SQLite для Phase 1)

### 1.1 Таблица: users
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    first_seen_at TEXT NOT NULL,  -- ISO datetime
    last_seen_at TEXT NOT NULL,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_users_last_seen ON users(last_seen_at);
```

**Назначение:** Регистрация пользователей персонажа

### 1.2 Таблица: chats
```sql
CREATE TABLE chats (
    chat_id TEXT PRIMARY KEY,
    chat_type TEXT NOT NULL,  -- "private", "group", "supergroup"
    title TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_chats_last_seen ON chats(last_seen_at);
```

**Назначение:** Регистрация чатов

### 1.3 Таблица: chat_participants
```sql
CREATE TABLE chat_participants (
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    left_at TEXT,  -- NULL if still member
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_participants_chat ON chat_participants(chat_id);
CREATE INDEX idx_participants_user ON chat_participants(user_id);
```

**Назначение:** Связь пользователей и чатов (для групповых чатов)

### 1.4 Таблица: conversations
```sql
CREATE TABLE conversations (
    message_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    channel TEXT NOT NULL,  -- "telegram", "desktop", "voice"
    timestamp TEXT NOT NULL,  -- ISO datetime
    role TEXT NOT NULL,  -- "user", "assistant", "system"
    content TEXT NOT NULL,
    reply_to_message_id TEXT,
    metadata TEXT,  -- JSON (attachments, etc.)
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
);

CREATE INDEX idx_conversations_user_chat ON conversations(user_id, chat_id, timestamp);
CREATE INDEX idx_conversations_chat ON conversations(chat_id, timestamp);
CREATE INDEX idx_conversations_timestamp ON conversations(timestamp);
CREATE INDEX idx_conversations_channel ON conversations(channel);
```

**Назначение:** Полная история сообщений (первичный источник данных)

### 1.5 Таблица: memory_pieces
```sql
CREATE TABLE memory_pieces (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,  -- "entity_description", "thought", "event", "fact", "other"
    content TEXT NOT NULL,
    confidence REAL NOT NULL,  -- -1.0 to 1.0
    importance REAL NOT NULL,  -- 0.0 to 1.0
    scope TEXT NOT NULL,  -- "private", "user", "chat", "shared", "global"
    
    -- Context
    user_id TEXT,  -- NULL for global/shared
    chat_id TEXT,  -- NULL for user/global
    channel TEXT,  -- "telegram", "desktop", "voice", NULL
    
    -- Provenance
    source_type TEXT NOT NULL,  -- "conversation", "consolidation", "migration", "manual"
    source_message_ids TEXT,  -- JSON array of message_ids
    
    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    
    -- Retrieval hints
    retrieval_cues TEXT,  -- JSON array
    entities TEXT,  -- JSON array
    
    -- Metadata
    metadata TEXT,  -- JSON
    
    -- Embedding stored separately (see memory_embeddings table)
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
);

CREATE INDEX idx_memory_scope ON memory_pieces(scope);
CREATE INDEX idx_memory_user ON memory_pieces(user_id, scope);
CREATE INDEX idx_memory_chat ON memory_pieces(chat_id, scope);
CREATE INDEX idx_memory_confidence ON memory_pieces(confidence);
CREATE INDEX idx_memory_importance ON memory_pieces(importance);
CREATE INDEX idx_memory_last_used ON memory_pieces(last_used_at);
CREATE INDEX idx_memory_kind ON memory_pieces(kind);
```

**Назначение:** Долговременная память (производная от conversations)

### 1.6 Таблица: memory_embeddings
```sql
CREATE TABLE memory_embeddings (
    memory_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,  -- numpy array as bytes
    embedding_model TEXT NOT NULL,  -- "text-embedding-3-small" etc.
    dimension INTEGER NOT NULL,  -- 1536, 3072, etc.
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memory_pieces(id) ON DELETE CASCADE
);

CREATE INDEX idx_embeddings_model ON memory_embeddings(embedding_model);
```

**Назначение:** Embeddings для vector retrieval (отдельная таблица для оптимизации)

### 1.7 Таблица: working_memory
```sql
CREATE TABLE working_memory (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    
    -- Current state
    current_topic TEXT,
    conversation_summary TEXT,
    emotion_state TEXT,
    
    -- Timestamps
    last_interaction_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    
    -- Metadata
    metadata TEXT,  -- JSON
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id),
    UNIQUE(user_id, chat_id, channel)
);

CREATE INDEX idx_working_memory_context ON working_memory(user_id, chat_id, channel);
CREATE INDEX idx_working_memory_last_interaction ON working_memory(last_interaction_at);
```

**Назначение:** Текущее состояние взаимодействия

### 1.8 Таблица: working_memory_items
```sql
CREATE TABLE working_memory_items (
    id TEXT PRIMARY KEY,
    working_memory_id TEXT NOT NULL,
    item_type TEXT NOT NULL,  -- "promise", "plan", "question", "task"
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- "active", "completed", "cancelled"
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    due_at TEXT,  -- For plans/tasks
    completed_at TEXT,
    metadata TEXT,  -- JSON
    
    FOREIGN KEY (working_memory_id) REFERENCES working_memory(id) ON DELETE CASCADE
);

CREATE INDEX idx_wm_items_working_memory ON working_memory_items(working_memory_id);
CREATE INDEX idx_wm_items_type_status ON working_memory_items(item_type, status);
CREATE INDEX idx_wm_items_due ON working_memory_items(due_at);
```

**Назначение:** Promises, plans, pending questions в working memory

### 1.9 Таблица: memory_relationships (опционально, Phase 2)
```sql
CREATE TABLE memory_relationships (
    id TEXT PRIMARY KEY,
    from_memory_id TEXT NOT NULL,
    to_memory_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,  -- "relates_to", "contradicts", "supports", etc.
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT,  -- JSON
    
    FOREIGN KEY (from_memory_id) REFERENCES memory_pieces(id) ON DELETE CASCADE,
    FOREIGN KEY (to_memory_id) REFERENCES memory_pieces(id) ON DELETE CASCADE
);

CREATE INDEX idx_relationships_from ON memory_relationships(from_memory_id);
CREATE INDEX idx_relationships_to ON memory_relationships(to_memory_id);
```

**Назначение:** Связи между memory pieces

### 1.10 Таблица: consolidation_log (опционально, для отладки)
```sql
CREATE TABLE consolidation_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    operation TEXT NOT NULL,  -- "merge", "split", "delete", "update_confidence"
    affected_memory_ids TEXT NOT NULL,  -- JSON array
    reason TEXT,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL
);

CREATE INDEX idx_consolidation_timestamp ON consolidation_log(timestamp);
```

**Назначение:** Аудит consolidation операций

## 2. Python Domain Models

### 2.1 User Model
```python
@dataclass
class User:
    user_id: str
    display_name: str
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### 2.2 Chat Model
```python
@dataclass
class Chat:
    chat_id: str
    chat_type: str  # "private", "group", "supergroup"
    title: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### 2.3 Conversation Message Model
```python
@dataclass
class ConversationMessage:
    message_id: str
    user_id: str
    chat_id: str
    channel: str  # "telegram", "desktop", "voice"
    timestamp: datetime
    role: str  # "user", "assistant", "system"
    content: str
    reply_to_message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### 2.4 Memory Piece Model (уже в interfaces/memory.py)
Использовать существующий `MemoryPiece`

### 2.5 Working Memory Context Model (уже в interfaces/memory.py)
Расширить существующий `WorkingMemoryContext`:

```python
@dataclass
class WorkingMemoryItem:
    id: str
    item_type: str  # "promise", "plan", "question", "task"
    content: str
    status: str = "active"  # "active", "completed", "cancelled"
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    due_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 3. Repository Layer (Data Access)

### 3.1 ConversationRepository
```python
class ConversationRepository:
    async def store_message(self, msg: ConversationMessage) -> None
    async def get_conversation_history(
        self, user_id: str, chat_id: str, 
        limit: int = 100, before: datetime | None = None
    ) -> list[ConversationMessage]
    async def get_message(self, message_id: str) -> ConversationMessage | None
    async def search_messages(
        self, query: str, user_id: str | None = None, 
        chat_id: str | None = None, limit: int = 50
    ) -> list[ConversationMessage]
```

### 3.2 MemoryRepository
```python
class MemoryRepository:
    async def create_memory(self, piece: MemoryPiece) -> str
    async def get_memory(self, memory_id: str) -> MemoryPiece | None
    async def update_memory(self, piece: MemoryPiece) -> bool
    async def delete_memory(self, memory_id: str) -> bool
    async def search_by_embedding(
        self, query_embedding: list[float],
        scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 10,
        min_confidence: float = -1.0
    ) -> list[tuple[MemoryPiece, float]]
    async def get_by_scope(
        self, scope: MemoryScope,
        user_id: str | None = None,
        chat_id: str | None = None,
        limit: int = 100
    ) -> list[MemoryPiece]
```

### 3.3 WorkingMemoryRepository
```python
class WorkingMemoryRepository:
    async def get_context(
        self, user_id: str, chat_id: str, channel: str
    ) -> WorkingMemoryContext
    async def update_context(
        self, user_id: str, chat_id: str, channel: str,
        updates: dict[str, Any]
    ) -> None
    async def add_item(
        self, user_id: str, chat_id: str, channel: str,
        item: WorkingMemoryItem
    ) -> str
    async def get_items(
        self, user_id: str, chat_id: str, channel: str,
        item_type: str | None = None,
        status: str = "active"
    ) -> list[WorkingMemoryItem]
    async def update_item(self, item_id: str, updates: dict[str, Any]) -> bool
    async def complete_item(self, item_id: str) -> bool
    async def clear_context(
        self, user_id: str, chat_id: str, channel: str
    ) -> None
```

### 3.4 UserRepository
```python
class UserRepository:
    async def create_user(self, user: User) -> None
    async def get_user(self, user_id: str) -> User | None
    async def update_user(self, user: User) -> bool
    async def get_or_create_user(
        self, user_id: str, display_name: str
    ) -> User
```

### 3.5 ChatRepository
```python
class ChatRepository:
    async def create_chat(self, chat: Chat) -> None
    async def get_chat(self, chat_id: str) -> Chat | None
    async def update_chat(self, chat: Chat) -> bool
    async def get_or_create_chat(
        self, chat_id: str, chat_type: str, title: str | None = None
    ) -> Chat
```

## 4. Retrieval Architecture

### 4.1 Context Resolver
```python
@dataclass
class RetrievalContext:
    # Identity
    user_id: str
    chat_id: str
    channel: str
    
    # Query
    query_text: str
    query_embedding: list[float]
    
    # Resolved access
    accessible_scopes: list[MemoryScope]
    is_desktop_owner: bool
    linked_user_ids: list[str]  # For cross-channel context
    linked_chat_ids: list[str]  # For user's other chats
    
    # Metadata
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

class ContextResolver:
    def __init__(self, config: Config):
        self.config = config
    
    async def resolve_context(
        self, user_id: str, chat_id: str, channel: str, query_text: str
    ) -> RetrievalContext:
        """Resolve retrieval context from request parameters."""
        # Determine accessible scopes
        scopes = [MemoryScope.GLOBAL]  # Always accessible
        
        # Add CHAT scope for current chat
        scopes.append(MemoryScope.CHAT)
        
        # Add USER scope for current user
        scopes.append(MemoryScope.USER)
        
        # Check if desktop owner
        is_desktop_owner = False
        if self.config.desktop_owner_telegram_id:
            is_desktop_owner = (user_id == self.config.desktop_owner_telegram_id)
        
        # Add PRIVATE scope for desktop owner
        if is_desktop_owner:
            scopes.append(MemoryScope.PRIVATE)
        
        # Get embedding for query
        # (will be implemented in memory service)
        
        return RetrievalContext(...)
```

### 4.2 Multi-level Retriever
```python
class MultiLevelRetriever:
    def __init__(
        self,
        memory_repo: MemoryRepository,
        working_memory_repo: WorkingMemoryRepository,
        context_resolver: ContextResolver
    ):
        self.memory_repo = memory_repo
        self.working_memory_repo = working_memory_repo
        self.context_resolver = context_resolver
    
    async def retrieve(
        self, ctx: RetrievalContext, max_pieces: int = 10
    ) -> list[MemoryPiece]:
        """Multi-level retrieval with scope filtering."""
        all_pieces = []
        
        # 1. Working memory (always first)
        # (not embedding-based, just current context)
        
        # 2. Chat memory
        if MemoryScope.CHAT in ctx.accessible_scopes:
            chat_pieces = await self.memory_repo.search_by_embedding(
                ctx.query_embedding,
                scope=MemoryScope.CHAT,
                chat_id=ctx.chat_id,
                limit=3
            )
            all_pieces.extend(chat_pieces)
        
        # 3. User memory
        if MemoryScope.USER in ctx.accessible_scopes:
            user_pieces = await self.memory_repo.search_by_embedding(
                ctx.query_embedding,
                scope=MemoryScope.USER,
                user_id=ctx.user_id,
                limit=3
            )
            all_pieces.extend(user_pieces)
        
        # 4. Cross-channel memory (for desktop owner)
        if ctx.is_desktop_owner and ctx.linked_user_ids:
            # Search across linked identities
            pass
        
        # 5. Global memory
        if MemoryScope.GLOBAL in ctx.accessible_scopes:
            global_pieces = await self.memory_repo.search_by_embedding(
                ctx.query_embedding,
                scope=MemoryScope.GLOBAL,
                limit=2
            )
            all_pieces.extend(global_pieces)
        
        # Deduplicate and rank
        deduplicated = self._deduplicate(all_pieces)
        ranked = self._rank_by_relevance(deduplicated, ctx)
        
        return ranked[:max_pieces]
    
    def _deduplicate(
        self, pieces: list[tuple[MemoryPiece, float]]
    ) -> list[tuple[MemoryPiece, float]]:
        """Remove duplicate memory pieces."""
        seen = set()
        result = []
        for piece, score in pieces:
            if piece.id not in seen:
                seen.add(piece.id)
                result.append((piece, score))
        return result
    
    def _rank_by_relevance(
        self, pieces: list[tuple[MemoryPiece, float]], ctx: RetrievalContext
    ) -> list[MemoryPiece]:
        """Rank pieces by combined score."""
        # Sort by: similarity + confidence_boost + importance_boost + recency_boost
        sorted_pieces = sorted(
            pieces,
            key=lambda x: (
                x[1]  # similarity score
                + x[0].confidence * 0.1
                + x[0].importance * 0.05
                + self._recency_score(x[0])
            ),
            reverse=True
        )
        return [p[0] for p in sorted_pieces]
    
    def _recency_score(self, piece: MemoryPiece) -> float:
        """Calculate recency boost (0.0 to 0.05)."""
        if not piece.last_used_at:
            return 0.0
        # More recent = higher score
        # (implementation details)
        return 0.0
```

## 5. Memory Service (High-level API)

```python
class MemoryService:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        memory_repo: MemoryRepository,
        working_memory_repo: WorkingMemoryRepository,
        retriever: MultiLevelRetriever,
        embedding_provider: IEmbeddingProvider,
        config: Config
    ):
        self.conversation_repo = conversation_repo
        self.memory_repo = memory_repo
        self.working_memory_repo = working_memory_repo
        self.retriever = retriever
        self.embedding_provider = embedding_provider
        self.config = config
    
    async def store_message(self, msg: ConversationMessage) -> None:
        """Store message in conversation history."""
        await self.conversation_repo.store_message(msg)
    
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
        source_message_ids: list[str] | None = None
    ) -> str:
        """Create memory piece from text."""
        # Generate embedding
        embedding = await self.embedding_provider.embedding(content)
        
        # Create memory piece
        piece = MemoryPiece(
            id=self._generate_id(),
            kind=kind,
            content=content,
            confidence=confidence,
            importance=importance,
            scope=scope,
            user_id=user_id,
            chat_id=chat_id,
            channel=channel,
            embedding=embedding.tolist(),
            source_type="conversation",
            source_message_ids=source_message_ids or [],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_used_at=None,
            usage_count=0
        )
        
        memory_id = await self.memory_repo.create_memory(piece)
        return memory_id
    
    async def retrieve_context(
        self,
        user_id: str,
        chat_id: str,
        channel: str,
        query_text: str,
        max_pieces: int = 10
    ) -> tuple[WorkingMemoryContext, list[MemoryPiece]]:
        """Retrieve full context for LLM prompt."""
        # Resolve context
        ctx = await self.retriever.context_resolver.resolve_context(
            user_id, chat_id, channel, query_text
        )
        
        # Get working memory
        working_ctx = await self.working_memory_repo.get_context(
            user_id, chat_id, channel
        )
        
        # Retrieve long-term memory
        memories = await self.retriever.retrieve(ctx, max_pieces)
        
        # Update usage statistics
        for memory in memories:
            memory.last_used_at = datetime.now(UTC)
            memory.usage_count += 1
            await self.memory_repo.update_memory(memory)
        
        return working_ctx, memories
    
    async def add_promise(
        self, user_id: str, chat_id: str, channel: str, promise: str
    ) -> str:
        """Add promise to working memory."""
        item = WorkingMemoryItem(
            id=self._generate_id(),
            item_type="promise",
            content=promise
        )
        return await self.working_memory_repo.add_item(
            user_id, chat_id, channel, item
        )
    
    async def add_plan(
        self, user_id: str, chat_id: str, channel: str, 
        plan: str, due_at: datetime | None = None
    ) -> str:
        """Add plan to working memory."""
        item = WorkingMemoryItem(
            id=self._generate_id(),
            item_type="plan",
            content=plan,
            due_at=due_at
        )
        return await self.working_memory_repo.add_item(
            user_id, chat_id, channel, item
        )
    
    def _generate_id(self) -> str:
        """Generate unique ID."""
        import uuid
        return str(uuid.uuid4())
```

## 6. Configuration Updates

Добавить в `config.py`:

```python
# Desktop owner linking (ТЗ-002 punkt 5)
desktop_owner_telegram_id: str | None = None  # Link desktop to Telegram user

# Memory system settings
memory_database_path: str = "data/memory.db"
memory_retrieval_limit: int = 10
memory_min_similarity: float = 0.7
memory_consolidation_enabled: bool = False  # Phase 2

# Working memory settings
working_memory_max_promises: int = 10
working_memory_max_plans: int = 20
working_memory_expiry_hours: int = 72  # Auto-clear after 72h inactive
```

## 7. Integration Points

### 7.1 Telegram Handler
```python
# After receiving message:
await memory_service.store_message(ConversationMessage(...))

# Before responding:
working_ctx, memories = await memory_service.retrieve_context(
    user_id=msg.user_id,
    chat_id=msg.chat_id,
    channel="telegram",
    query_text=msg.text
)

# Build prompt with working_ctx + memories
```

### 7.2 Desktop Handler (future)
```python
# Same API, different channel
working_ctx, memories = await memory_service.retrieve_context(
    user_id=desktop_owner_id,
    chat_id="desktop",
    channel="desktop",
    query_text=query
)
```

## 8. Migration Tool (Placeholder for Phase 2)

```python
class DiaryMigrator:
    async def migrate_from_diary(
        self, diary_dir: Path, target_user_id: str
    ) -> dict[str, Any]:
        """Migrate old diary entries to new memory system."""
        # Read old diary entries
        # Convert to MemoryPiece with scope=GLOBAL or USER
        # Preserve confidence, embeddings
        # Mark source_type="migration"
        # Return statistics
        pass
```

---

**Статус:** Этап 2 (Проектирование) завершён
**Следующий:** Этап 3 (Реализация инфраструктуры)
