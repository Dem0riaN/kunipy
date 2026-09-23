# Repository and documentation audit

**Audit date:** 2026-09-23

## Method

The repository was reviewed against the current GitHub source, with particular
attention to:

- root README;
- `pyproject.toml`;
- `config.example.toml`;
- `src/config.py`;
- `src/app.py`;
- memory implementation;
- Telegram client;
- proxy;
- character system;
- metrics;
- desktop scaffolding;
- current architecture documentation.

The audit was performed against the repository's current remote source. The
complete test suite was not executed locally during this audit.

## Major findings

### 1. The old README was stale

The old README described the memory subsystem as mostly a stub and listed
future work that is now implemented.

The current source contains:

- `MemoryService`;
- ChromaDB vector storage;
- SQLite repositories;
- automatic memory formation;
- memory-integrated workers;
- working memory;
- diary context injection.

Therefore the old "stub memory" description should be removed.

### 2. The project is no longer accurately described as a simple port

The repository contains substantial Python-specific work and new subsystems.
The README should describe the project as based on/inspired by `kuni`, not as
a straightforward Python port.

### 3. Version information is inconsistent

The root README currently states:

```text
Current Version: 0.5.0
```

while `pyproject.toml` declares:

```toml
version = "0.1.0"
```

The new documentation intentionally avoids asserting a project version until
the package metadata and release process are synchronized.

### 4. Configuration is not fully synchronized

`config.example.toml` is large and useful, but it contains historical naming
and comments that do not always match `src/config.py`.

One visible example is image generation:

- example: `capabilities.image_generation`;
- serializer: `capabilities.generate_images`.

The example also contains a note that not all parameters have been integrated
into the new Config structure.

Therefore the implementation parser is the final reference for configuration.

### 5. Architecture documentation is ahead of the code in places

The architecture document describes a clean four-layer system, while the code
still contains legacy top-level modules and a compatibility `get_config()`
singleton.

The new documentation describes this as a hybrid/refactoring state.

### 6. Desktop support exists, but should not be advertised as a complete
desktop application

The `src/desktop` package exists and is designed around lazy imports and
graceful degradation. The project metadata does not install a full desktop
runtime by default.

It is more accurate to call this an experimental/scaffolded desktop-character
layer.

### 7. Proxy functionality is real

The proxy is not merely planned. `src/proxy_server.py` implements a FastAPI
server, intercepts chat completions, injects persona/tools, executes a local
tool loop, and forwards other compatible endpoints upstream.

Its streaming behaviour is intentionally simplified.

### 8. Metrics are real

The repository contains Prometheus counters for LLM usage and a `/metrics`
HTTP endpoint. The configured application port is used when the metrics server
is started.

### 9. The original README mixed languages

The old README mixes English, Russian and technical notes. The new structure
uses English as the canonical technical language and provides separate
Russian, Chinese and Japanese entry points.

### 10. Licensing requires special care

The upstream `kuni` repository did not have a license at the time the Kunipy
work was started, according to the maintainer's project history.

That means a new license cannot safely be treated as granting rights to all
upstream-derived material. The supplied `LICENSE` therefore distinguishes
Kunipy's original material from inherited third-party material.

If full-repository redistribution rights are required, the safest route is to
obtain explicit permission from the original copyright holder for inherited
code.

## Documentation policy going forward

When changing the project:

1. Update code first.
2. Verify the actual behaviour.
3. Update `config.example.toml`.
4. Update detailed docs.
5. Keep the root README short.
6. Do not document roadmap items as current features.
7. Keep translated READMEs synchronized with the canonical README.
