# Kunipy - AI Character with Long-term Memory

Kunipy is a conversational AI character with persistent memory, supporting Telegram, desktop, and voice channels.

## Features

### Core Capabilities
- **Multi-channel Communication**: Telegram, desktop client, voice interactions
- **Hybrid Memory System**: SQLite (WAL mode) + ChromaDB (HNSW vector search) for long-term memory
- **Automatic Memory Formation**: LLM-based extraction of facts, events, thoughts from conversations
- **Cross-channel Context**: Desktop owner's memories shared across all channels
- **Working Memory**: In-memory short-term context with `.md` file persistence (promises, plans, pending questions)
- **Conversation History**: Full message storage with provenance tracking in SQLite

### Memory System (ТЗ-002)

**Hybrid Architecture (SQLite + ChromaDB):**
- **ChromaDB**: HNSW approximate nearest neighbor (ANN) vector search for fast semantic retrieval
- **SQLite (WAL mode)**: Metadata, links, tags, user preferences, conversation history
- **Dual-write pattern**: `MemoryService.create_memory()` writes to both stores atomically
- Multi-level memory hierarchy (working memory, long-term memory, conversation history)
- Scope-based visibility (PRIVATE, USER, CHAT, SHARED, GLOBAL)
- Automatic consolidation and importance scoring
- Cross-channel context linking for desktop owner

**Components:**
- `MemoryService` - High-level API with dual-write (ChromaDB + SQLite)
- `MemoryFormationService` - LLM-based automatic memory extraction
- `MemoryIntegratedWorker` - Worker with transparent memory integration
- `MemoryStore` - ChromaDB wrapper for vector search (HNSW ANN)
- `MemoryRepository` - SQLite metadata storage
- `MemoryLinkRepository` - Entity relationships (SQLite)
- `UserPreferenceRepository` - User preferences (SQLite)
- `MemoryTagRepository` - Memory tags (SQLite)
- `ConversationRepository` - Message history (SQLite)
- `WorkingMemory` - In-memory context with `.md` file persistence

### Legacy Support
- **kuni Archive Reader**: Read C++ kuni diary format (markdown + JSON metadata)
- **Migration Tool**: Convert legacy memories to kunipy format
- **Memory Exporter**: Export to JSON/JSONL/Markdown formats

## Quick Start

### Prerequisites
- Python 3.12+
- OpenAI-compatible API endpoint
- Telegram API credentials (optional)

**Note:** kunipy uses SQLite with WAL mode for metadata and ChromaDB for vector search. No external database server required.

### Installation

```bash
# Clone repository
cd kunipy

# Install dependencies
python -m pip install -r requirements.txt

# Configure
cp config.toml.example config.toml
# Edit config.toml with your settings
```

### Configuration

**Essential settings in `config.toml`:**

```toml
# LLM endpoint
[llm]
base_url = "http://localhost:1234/v1"
model = "llama-3.3-70b"

# Embedding endpoint
[embedding]
base_url = "http://localhost:1234/v1"
model = "text-embedding-3-large"

# Memory system (hybrid SQLite + ChromaDB)
memory_enabled = true
memory_db_path = "data/memory.db"  # SQLite metadata
memory_min_similarity = 0.5

# Desktop owner (for cross-channel context)
desktop_owner_telegram_id = "telegram:123456789"
```

### Running

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Run application
python run.py
```

### Memory Tools

**Migrate from C++ kuni:**
```bash
python migrate_kuni.py --kuni-dir ./old_diary --dry-run
python migrate_kuni.py --kuni-dir ./old_diary --scope global
```

**Export memories:**
```bash
# Export to JSON
python export_memory.py --output memory.json

# Export to Markdown (human-readable)
python export_memory.py --output memory.md --format markdown

# Filter by scope/user
python export_memory.py --output user_memories.json --user-id telegram:12345
```

## Architecture

### Project Structure

```
kunipy-main/
├── src/
│   ├── app.py                      # Main application entry
│   ├── worker.py                   # Base worker logic
│   ├── memory_integrated_worker.py # Worker with memory integration
│   ├── character.py                # Character prompt building
│   ├── config.py                   # Configuration management
│   ├── openai_chat.py              # LLM client
│   ├── telegram_client.py          # Telegram integration
│   ├── notification_manager.py     # Event coordination
│   ├── domain/
│   │   └── memory_models.py        # Memory domain models
│   ├── interfaces/
│   │   ├── llm.py                  # LLM interface protocols
│   │   └── memory.py               # Memory interface protocols
│   ├── infrastructure/
│   │   ├── memory/
│   │   │   ├── memory_service.py           # High-level memory API (dual-write)
│   │   │   ├── memory_formation.py         # Automatic memory extraction
│   │   │   ├── storage.py                  # MemoryStore (ChromaDB wrapper)
│   │   │   ├── vector_store.py             # ChromaDB vector operations
│   │   │   ├── memory_repository.py        # SQLite metadata storage
│   │   │   ├── memory_link_repository.py   # Entity relationships (SQLite)
│   │   │   ├── user_preference_repository.py # User preferences (SQLite)
│   │   │   ├── memory_tag_repository.py    # Memory tags (SQLite)
│   │   │   ├── conversation_repository.py  # Message history (SQLite)
│   │   │   ├── working_memory.py           # In-memory context + .md persistence
│   │   │   ├── database.py                 # SQLite schema & connection
│   │   │   ├── kuni_archive_reader.py      # Legacy C++ kuni format reader
│   │   │   ├── kuni_migrator.py            # Migration: C++ kuni → kunipy
│   │   │   └── memory_exporter.py          # Export to JSON/JSONL/Markdown
│   │   └── embedding_adapter.py    # OpenAI embedding adapter
│   └── di/
│       └── container.py            # Dependency injection
├── migrate_kuni.py                 # CLI migration tool
├── export_memory.py                # CLI export tool
├── config.toml                     # Configuration
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

### Memory System Design

**Memory Piece Structure:**
```python
MemoryPiece(
    id: str,                    # UUID
    kind: MemoryKind,           # fact, event, thought, entity_description, other
    content: str,               # Human-readable content
    confidence: float,          # -1 to 1 (lie, uncertain, confirmed)
    importance: float,          # 0 to 1
    scope: MemoryScope,         # private, user, chat, shared, global
    user_id: str | None,        # Owner (for USER/CHAT scope)
    chat_id: str | None,        # Chat context (for CHAT scope)
    channel: str,               # telegram, desktop, voice
    embedding: list[float],     # Vector for similarity search
    source_type: str,           # conversation, migration, manual
    source_message_ids: list,   # Provenance
    created_at: datetime,
    updated_at: datetime,
    last_used: datetime,
    usage_count: int,
    entities: list[str],        # Named entities mentioned
    metadata: dict,             # Additional context
)
```

**Scope Visibility:**
- PRIVATE: Only desktop owner on desktop channel
- USER: Specific user across all channels
- CHAT: All participants in specific chat
- SHARED: All users in specific channel
- GLOBAL: Everyone everywhere

**Retrieval Strategy (ChromaDB HNSW):**
1. Generate query embedding from user message
2. Resolve accessible scopes (based on user permissions)
3. Resolve linked user IDs (cross-channel for owner)
4. Multi-level search via ChromaDB HNSW: CHAT (3) → USER (3) → PRIVATE (2) → GLOBAL (2)
5. Deduplicate by ID
6. Rank by similarity score
7. Return top N pieces

**Dual-Write Pattern:**
- `MemoryService.create_memory()` writes to ChromaDB (vectors) first, then SQLite (metadata)
- Ensures consistency: ChromaDB for fast search, SQLite for transactions and relationships
- SQLite WAL mode enables concurrent reads + single writer without blocking

### Worker Integration

`MemoryIntegratedWorker` extends base `Worker`:

1. **Before LLM call** (`_build_system_prompt`):
   - Retrieve relevant memories via semantic search
   - Format as text block
   - Inject into system prompt

2. **After user message** (`_process_notification`):
   - Store message in conversation history
   - Generate LLM response
   - Extract new memories from recent exchanges
   - Generate embeddings
   - Store memories with provenance

## Development

### Code Quality

```bash
# Lint with ruff
ruff check .

# Auto-fix issues
ruff check . --fix

# Format
ruff format .
```

### Testing

```bash
# Test memory formation
python test_memory_formation.py

# Test simple memory operations
python test_memory_simple.py

# Test full Worker integration
python test_memory_worker_integration.py
```

### Database Schema (SQLite + ChromaDB)

**SQLite tables (metadata & relationships):**
- `memory_pieces` - Long-term memories (metadata only, embeddings in ChromaDB)
- `memory_embeddings` - Embedding vectors (BLOB, backup/recovery)
- `memory_links` - Entity relationships (§35 ТЗ-002)
- `memory_tags` - Memory categorization tags
- `user_preferences` - User-specific preferences
- `conversation_messages` - Full message history
- `users` - User profiles
- `chats` - Chat metadata

**ChromaDB collections (vector search):**
- `memories` - HNSW index for fast approximate nearest neighbor search

See `src/infrastructure/memory/database.py` for SQLite schema.

## Configuration Reference

### Memory Settings

```toml
# Enable/disable memory system
memory_enabled = true

# SQLite database path (metadata, links, tags, preferences)
memory_db_path = "data/memory.db"

# Minimum similarity for retrieval (0-1)
memory_min_similarity = 0.5

# Maximum conversation history to store
memory_max_history = 1000

# Desktop owner for cross-channel linking
desktop_owner_telegram_id = "telegram:123456789"
```

**Note:** ChromaDB vector index is stored in `data/chroma/` (same directory as SQLite db).

### LLM Settings

```toml
[llm]
base_url = "http://localhost:1234/v1"
model = "llama-3.3-70b"
bearer_key = ""  # Optional API key

[embedding]
base_url = "http://localhost:1234/v1"
model = "text-embedding-3-large"
bearer_key = ""
```

### Telegram Settings

```toml
telegram_enabled = true
telegram_api_id = 12345
telegram_api_hash = "your_hash"
telegram_phone_number = "+1234567890"
telegram_database_directory = "data/tdlib"
```

## Troubleshooting

### Memory not working

1. Check `memory_enabled = true` in config.toml
2. Verify SQLite database exists at `data/memory.db`
3. Verify ChromaDB index exists at `data/chroma/`
4. Ensure embedding endpoint is accessible
5. Check logs for errors: `memory_service.log`

### Performance issues

1. ChromaDB HNSW is optimized for vector search (sub-100ms for <100K memories)

2. Tune retrieval parameters:
   ```toml
   memory_min_similarity = 0.4  # Higher = fewer results
   ```

3. SQLite WAL mode enables concurrent reads without blocking writers

4. For >1M memories, consider archiving old entries

### Migration issues

1. Verify legacy diary format:
   ```bash
   python migrate_kuni.py --kuni-dir ./diary --stats
   ```

2. Dry-run first:
   ```bash
   python migrate_kuni.py --kuni-dir ./diary --dry-run
   ```

3. Check embedding dimensions match (4096 for text-embedding-3-large)

## Technical Specifications

### Implementation Status (ТЗ-002)

**✅ Completed (80%):**
- Multi-level memory hierarchy
- Scope-based visibility
- Vector similarity search
- Automatic memory formation
- Cross-channel context
- Legacy archive reader
- Migration tools
- Export utilities
- Runtime integration

**⏳ Remaining (20%):**
- Consolidation algorithm
- Entity relationship graph
- Diagnostic tools
- Comprehensive test suite

### Performance Characteristics

**Memory Formation:**
- LLM call per 6 messages (configurable)
- ~1-2 seconds per extraction
- Async/non-blocking

**Memory Retrieval (ChromaDB HNSW):**
- Vector search: 10-50ms (ChromaDB HNSW ANN)
- Multi-level search: 4 queries in parallel
- Total: ~100-200ms

**Storage:**
- ~1KB per memory piece (SQLite metadata, excluding embedding)
- ~16KB per embedding (4096 dimensions, float32, ChromaDB)
- Conversation messages: ~500 bytes average (SQLite)

### Dependencies

**Core:**
- aiohttp - Async HTTP client
- numpy - Numerical operations
- chromadb - Vector database with HNSW indexing
- aiosqlite - SQLite adapter (async, WAL mode)

**Optional:**
- aiotdlib - Telegram client
- Pillow - Image processing

See `requirements.txt` for full list.

## License

See LICENSE file.

## Contributing

1. Follow existing code style (ruff formatting)
2. Add tests for new features
3. Update documentation
4. Keep memory system backward-compatible

## Support

- Issues: [GitHub Issues](https://github.com/your-repo/kunipy/issues)
- Documentation: See `docs/` directory
- ТЗ-002 Spec: See `TZ-002.md`

---

**Current Version:** 0.5.0 (Hybrid Memory + Phase 2/4: Sleep Consolidation + Auto-RAG)  
**Last Updated:** 2026-09-13
