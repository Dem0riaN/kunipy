# Configuration

The current configuration has two important sources:

1. `src/config.py` — what the application actually parses and stores.
2. `config.example.toml` — the user-facing example.

They are **not perfectly synchronized**. When they disagree, the parser in
`src/config.py` is the implementation reference.

## Core sections

### `[app]`

Currently used:

- `timezone`

### `[llm]`

Contains the main OpenAI-compatible model and endpoint:

```toml
[llm]
model = "your-model"

[llm.endpoint]
base_url = "http://localhost:11434/v1/"
bearer_key = ""
```

The HTTP client sends requests to `/chat/completions`.

### `[embedding]`

Controls the embedding model and endpoint used by memory/diary retrieval.

```toml
[embedding]
model = "nomic-embed-text"

[embedding.endpoint]
base_url = "http://localhost:11434/v1/"
bearer_key = ""
```

### `[character]`

Controls the default character name/nickname.

The character prompt itself is stored in editable Markdown files rather than
being hard-coded exclusively in TOML.

### `[telegram]`

Controls TDLib/Telegram integration:

```toml
[telegram]
enabled = true
api_id = 0
api_hash = ""
phone = ""
database_directory = "data/tdlib"
```

### `[memory]`

Controls the newer hybrid memory subsystem:

```toml
[memory]
enabled = true
db_path = "data/memory.db"
min_similarity = 0.5
desktop_owner_telegram_id = ""
```

The implementation uses ChromaDB for vector storage/search and SQLite for
structured metadata and repositories.

### `[diary]`

The repository still contains a separate Markdown diary path.

Important fields include:

- `enabled`
- `directory`
- `min_relatedness`
- `plagiarism_threshold`
- `chroma_dir`
- `embedding_dimension`
- `auto_rag_enabled`
- `context_token_threshold`
- `max_context_entries`
- `max_merge_span_days`
- `knn_soft_limit`
- `sleep_chance`

The diary and the newer memory system coexist in the current implementation.

### `[lockdown]`

Access-control modes include:

- `none`
- `contacts_only`
- `papik_only`

The configuration also supports notification filtering.

### `[capabilities.*]`

The repository has configuration paths for:

- hearing / speech recognition;
- vision;
- image generation;
- web search;
- stickers;
- camera/photo;
- voice recording / TTS;
- joining chats;
- leaving chats.

These are capability switches, not guarantees that an external backend is
available.

### `[proxy]`

The OpenAI-compatible proxy can be enabled independently.

The current application starts it on the configured port and binds Uvicorn to
`0.0.0.0`. See [`proxy.md`](proxy.md).

### `[worker]`

Controls background worker behaviour, including:

- sleep consolidation;
- random sleep;
- automatic diary save;
- worker count.

### `[metrics]`

Prometheus metrics can be enabled and exposed on the configured port.

The implementation exposes `/metrics`.

## Configuration drift found during audit

The example file contains historical/legacy names and comments. One important
example is image generation:

- the example uses `[capabilities.image_generation]`;
- the configuration serializer currently writes
  `[capabilities.generate_images]`.

There are also comments explicitly stating that some parameters have not yet
been integrated into the new `Config` structure.

Therefore, copy the example and verify each setting against the current
`src/config.py` before relying on it in automation.
