# Repository audit

This document records the documentation-oriented audit performed while
rewriting the README.

## Main findings

### README and version information

The old README contained claims that were not consistently aligned with the
current repository. In particular, version information should not be copied
from the README without checking the package metadata.

### Memory

The old documentation understated the implementation. The repository contains
an actual memory subsystem using persistent storage and semantic retrieval,
including SQLite/ChromaDB-related components and workers.

### Architecture

The project has a layered architecture, but it also retains compatibility and
legacy paths. Documentation should therefore avoid presenting it as a
perfectly strict Clean Architecture implementation.

### Proxy and metrics

Proxy and metrics components exist in the current implementation and should be
documented as implemented subsystems rather than future roadmap items.

### Desktop

Desktop-related code should be described conservatively as current project
work. It should not be attributed to Kuni.

### Configuration

The example configuration and implementation must be kept synchronized. When
they disagree, the source code is the final technical reference until the
configuration is corrected.

## Documentation rule

Future README changes should follow this order:

1. inspect the implementation;
2. verify the claim;
3. document only the verified behaviour;
4. mark experimental/incomplete functionality explicitly;
5. keep detailed implementation notes in `docs/`.

The README is an introduction, not the source of truth for implementation
details.
