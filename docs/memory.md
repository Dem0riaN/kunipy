# Memory

The current memory subsystem is an implemented part of Kunipy rather than an
empty placeholder.

It includes persistent storage and semantic retrieval, with SQLite and
ChromaDB used by the current implementation.

Relevant source areas include:

- `src/infrastructure/memory/`
- memory services and repositories;
- memory-related workers;
- application integration.

## Important distinction

Memory behaviour depends on configuration, embedding/model availability and
the runtime environment. Presence of the implementation does not mean every
deployment has the same memory behaviour.

For implementation details, inspect the current memory service and worker
code rather than relying on older README descriptions.
