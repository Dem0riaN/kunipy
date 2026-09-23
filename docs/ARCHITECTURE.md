# Architecture

Kunipy currently uses a layered Python architecture with application, domain,
interfaces and infrastructure components.

The repository also contains compatibility/legacy modules, so the source tree
should not be treated as a perfectly isolated Clean Architecture reference
implementation.

## High-level model

```text
interfaces / entry points
        |
        v
application services
        |
        v
domain abstractions
        |
        v
infrastructure
        |
        +-- LLM / models
        +-- memory
        +-- Telegram
        +-- proxy
        +-- media / speech
        +-- metrics
```

The exact dependency graph is implementation-defined and should be checked
against the current imports when making architectural changes.

## Compatibility code

Some older access paths remain for compatibility. In particular, configuration
access is not limited to a single modern dependency-injection path.

## Desktop

Desktop/character UI work is separate from the original Kuni project. It is
part of Kunipy's own direction and should not be described as functionality
inherited from Kuni.
