# Memory and diary

Kunipy currently has two related but distinct persistence systems.

## 1. Hybrid memory

The newer memory subsystem uses:

- ChromaDB for semantic/vector search;
- SQLite for structured metadata;
- working memory for short-lived state;
- repositories for conversations, users, chats, preferences, links and tags.

`MemoryService.create_memory()` performs a vector-store write followed by an
SQLite metadata write.

Retrieval uses semantic search with scope filtering.

Current scopes include:

- `CHAT`
- `USER`
- `PRIVATE`
- `GLOBAL`

The service resolves accessible scopes and then deduplicates/ranks results.

## 2. Legacy diary

The Markdown diary remains active.

The current worker can combine:

1. the newer memory context;
2. legacy diary Auto-RAG context.

This is important because the project is in a migration/hybrid state rather
than having a single unified memory implementation.

## Automatic formation

`MemoryIntegratedWorker`:

1. retrieves memory context before generation;
2. processes the message;
3. takes recent conversation messages;
4. sends them through `MemoryFormationService`;
5. generates embeddings;
6. stores extracted memory in the hybrid memory backend.

The current code therefore does contain a working automatic-memory path; the old
README statement that the memory system is only a stub is stale.

## Working memory

Working memory is used for short-lived information such as:

- promises;
- plans;
- pending context.

It is distinct from long-term semantic memory.

## Important caveat

Memory behaviour is highly dependent on the configured embedding endpoint and
LLM. Documentation should therefore avoid promising a specific "memory
quality" or exact semantic behaviour.
