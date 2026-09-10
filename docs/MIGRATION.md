# Migration Guide: C++ kuni → kunipy

This guide explains how to migrate your existing C++ kuni diary and memory data to the new kunipy memory system.

---

## Overview

The migration script converts:
- **Diary entries** from C++ kuni text format → kunipy `MemoryPiece`
- **User facts and context** → Scoped memory (USER/CHAT/GLOBAL)
- **Conversation history** → Event memories
- **Embeddings** → Regenerated using your configured embedding provider

---

## Prerequisites

1. **Backup your data** before running migration
2. kunipy installed with dependencies (ChromaDB included in requirements)
3. Have access to your C++ kuni diary directory (typically `~/.kuni/diary/` or similar)
4. Configure your embedding provider in `config.toml`

---

## Quick Start

### ✅ Automatic Migration (One Command)

The easiest way to migrate is using the built-in CLI script:

```bash
# Basic migration (automatic)
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary

# Dry-run (check before migrating)
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --dry-run

# Custom output directory
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --output-dir ./data/custom

# Verbose output
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --verbose

# Custom config file
python migrate_diary.py --kuni-dir /path/to/cpp-kuni/diary --config custom_config.toml
```

The script automatically:
- Scans all `*.txt` files in C++ kuni diary directory
- Parses metadata (confidence, importance, user_id, chat_id)
- Generates embeddings via configured LLM
- Saves to ChromaDB with progress tracking
- Shows statistics on completion

### Example Output

```
📋 Загрузка конфигурации: config.toml
🔧 Инициализация embedding provider...
📁 Output директория: D:\AI\kunipy-main\data\chroma
🔍 Сканирование C++ kuni diary: D:\kuni\diary
📊 Найдено файлов для миграции: 150

🚀 Начало миграции...

[Progress bar: 100%]

✅ Миграция завершена успешно!
   Мигрировано записей: 148
   ChromaDB location: D:\AI\kunipy-main\data\chroma

💡 Для использования обновите config.toml:
   [diary]
   directory = "D:\AI\kunipy-main\data\chroma"
```

---

## Advanced Usage

### Programmatic Migration

If you need more control, use the migration framework directly:

```python
import asyncio
from pathlib import Path
from src.config import load_config
from src.openai_chat import OpenAIChat
from src.infrastructure.memory import MemoryStore
from src.tools.migrate_legacy_diary import LegacyDiaryMigrator

async def run_migration():
    # Load config
    config = load_config("config.toml")
    
    # Initialize embedding provider
    openai_chat = OpenAIChat(endpoint=config.llm)
    
    # Initialize memory store
    memory_store = MemoryStore(persist_directory="./data/chroma")
    
    # Create migrator
    migrator = LegacyDiaryMigrator(
        kuni_diary_dir=Path("/path/to/kuni/diary"),
        embedding_provider=openai_chat,
    )
    
    # Run migration with progress
    memories = await migrator.migrate_all(
        target_store=memory_store,
        show_progress=True,
    )
    
    print(f"✅ Migrated {len(memories)} entries")

if __name__ == "__main__":
    asyncio.run(run_migration())
```

---

## C++ kuni Diary Format

The migrator expects C++ kuni diary entries in this format:

### File Naming Convention

```
YYYY-MM-DD_HH-MM-SS_description.txt
```

Examples:
- `2026-09-10_14-30-00_conversation.txt`
- `2024-01-15_09-45-30_user_fact.txt`

### File Content Format

```
confidence: 1.0
importance: 0.8
user_id: 123456789
chat_id: -987654321

This is the actual content of the memory piece.
Can be multiple lines.

fact: User prefers tea over coffee
thought: This might be relevant for recommendations
```

**Metadata fields** (optional):
- `confidence:` - Float from -1 (lie) to 1 (ground truth)
- `importance:` - Float from 0.0 to 1.0
- `user_id:` - Telegram user ID
- `chat_id:` - Telegram chat ID

**Content markers** (affects `MemoryKind`):
- `fact:` → `MemoryKind.FACT`
- `thought:` → `MemoryKind.THOUGHT`
- `entity:` → `MemoryKind.ENTITY_DESCRIPTION`
- (default) → `MemoryKind.EVENT`

---

## Migration Options

### Command-Line Arguments

```bash
python -m src.tools.migrate_legacy_diary --help
```

**Available options**:
- `--kuni-dir PATH` - Path to C++ kuni diary directory (required)
- `--output PATH` - Output path for migration report JSON (default: `./data/migration_report.json`)
- `--log-level LEVEL` - Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)

### Programmatic API

```python
from src.tools.migrate_legacy_diary import LegacyDiaryMigrator

migrator = LegacyDiaryMigrator(
    kuni_diary_dir=Path("/path/to/kuni/diary"),
    embedding_provider=openai_chat,
)

# Run migration
memories = await migrator.migrate()

# Check statistics
print(migrator.stats)
# {
#     "entries_processed": 150,
#     "entries_migrated": 148,
#     "errors": 2
# }
```

---

## Migration Report

After migration, inspect `migration_report.json`:

```json
[
  {
    "id": "uuid-here",
    "kind": "fact",
    "content": "User prefers tea over coffee",
    "confidence": 1.0,
    "importance": 0.8,
    "created_at": "2024-01-15T09:45:30+00:00",
    "scope": "private",
    "user_id": "123456789",
    "chat_id": "-987654321",
    "metadata": {
      "legacy_filename": "2024-01-15_09-45-30_user_fact.txt"
    }
  }
]
```

Use this to:
- Verify migration correctness
- Manually adjust metadata if needed
- Identify problematic entries

---

## Memory Scopes

Migrated memories are assigned scopes based on metadata:

| Metadata Present | Assigned Scope |
|-----------------|----------------|
| `user_id` + `chat_id` | `MemoryScope.CHAT` |
| `user_id` only | `MemoryScope.USER` |
| Neither | `MemoryScope.PRIVATE` |

To change scope after migration:

```python
memory = await memory_store.get_memory(memory_id)
memory.scope = MemoryScope.GLOBAL
await memory_store.update_memory(memory)
```

---

## Troubleshooting

### Issue: "No time zone found with key UTC"

**Solution**: Install `tzdata` package:
```bash
pip install tzdata
```

### Issue: "ModuleNotFoundError: No module named 'chromadb'"

**Solution**: Install ChromaDB:
```bash
pip install chromadb
```

### Issue: Entries not migrating

**Check**:
1. File naming follows `YYYY-MM-DD_HH-MM-SS_*.txt` format
2. Files are UTF-8 encoded
3. Check migration report JSON for error details
4. Run with `--log-level DEBUG` for detailed logs

### Issue: Out of memory during migration

**Solution**: Migrate in batches:

```python
import asyncio
from pathlib import Path

async def migrate_batch(entry_paths, start, end):
    batch = entry_paths[start:end]
    for path in batch:
        memory = await migrator._migrate_entry(path)
        if memory:
            await memory_store.create_memory(memory)

# Process 100 entries at a time
all_entries = list(kuni_dir.glob("*.txt"))
for i in range(0, len(all_entries), 100):
    await migrate_batch(all_entries, i, i+100)
    print(f"Processed {min(i+100, len(all_entries))}/{len(all_entries)}")
```

---

## Post-Migration

### 1. Verify Migration

```python
# Count migrated memories
from src.infrastructure.memory import MemoryStore

store = MemoryStore("./data/chroma")
count = await store._store.count()
print(f"Total memories in database: {count}")
```

### 2. Test Semantic Search

```python
# Search for memories about tea
query = "What does the user like to drink?"
embedding = await openai_chat.embedding(query)
results = await store.search_memory(
    query_embedding=embedding,
    scope=MemoryScope.USER,
    limit=5
)

for memory in results:
    print(f"[{memory.kind.value}] {memory.content}")
```

### 3. Clean Up

Once verified, you can:
- Keep original C++ kuni diary as backup
- Remove `migration_report.json` if no longer needed
- Archive old diary files

---

## Performance Notes

- **Embedding Generation**: ~1-2 seconds per entry (depends on API)
- **ChromaDB Indexing**: Fast, incremental
- **Batch Size**: Process 100-500 entries at a time for optimal memory usage
- **Caching**: Use `EmbeddingCache` to avoid re-generating embeddings for duplicate content

### Example with Caching

```python
from src.infrastructure.memory import EmbeddingCache

cache = EmbeddingCache(ttl_seconds=3600)

# Wrap embedding provider
class CachedEmbedder:
    def __init__(self, provider, cache):
        self.provider = provider
        self.cache = cache
    
    async def embedding(self, text: str) -> list[float]:
        cached = self.cache.get(text)
        if cached:
            return cached
        
        embedding = await self.provider.embedding(text)
        self.cache.set(text, embedding)
        return embedding

# Use in migration
cached_embedder = CachedEmbedder(openai_chat, cache)
memories = await migrate_legacy_diary(kuni_dir, cached_embedder)

# Check cache stats
print(cache.get_stats())
# {'hits': 15, 'misses': 135, 'size': 135, 'hit_rate': 0.1}
```

---

## Next Steps

After migration:
1. Configure memory retrieval in your config.toml
2. Test conversation flow with migrated context
3. Set up sleep consolidation for ongoing memory management
4. Monitor memory usage and quality

See [ARCHITECTURE.md](./ARCHITECTURE.md) for memory system architecture details.
