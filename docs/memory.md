# Memory

Kunipy currently has a real hybrid memory implementation. Older documentation describing the entire system as a stub is obsolete.

## Storage model

The current memory service uses:

- **ChromaDB** for vector/semantic retrieval;
- **SQLite** for structured metadata and conversation history;
- working-memory persistence;
- repositories for conversations, memories, links, tags, users, chats and preferences.

The service performs dual writes to ChromaDB and SQLite. citeturn4view0turn8view0

## Retrieval

The current implementation resolves accessible scopes and retrieves memories from chat, user, private and global scopes before deduplication and ranking. citeturn4view0

This should not be described as a completed implementation of a hypothetical “six-level retrieval” design unless that design is actually present in the current code.

## Automatic formation

After an interaction, `MemoryIntegratedWorker` can pass recent conversation messages to `MemoryFormationService`. The service asks the LLM to extract facts, events, thoughts, entity descriptions and relationships, then the worker embeds and stores the resulting memory pieces. citeturn9view3turn9view4

## Legacy stub

`src/infrastructure/memory/stub_store.py` remains in the repository as a legacy stub, but the current DI container uses the real `MemoryStore` implementation instead. citeturn4view1turn8view0
