# Architecture

Kunipy currently uses a layered application architecture with dependency injection.

## Main layers

```text
Application / orchestration
        |
        v
Domain models and protocols
        |
        v
Interfaces
        |
        v
Infrastructure
```

The composition root is `src/di/container.py`. It creates the LLM client, Telegram client, memory stores/services, diary services, media extractor registry, workers and other runtime components. citeturn8view0

`src/app.py` owns lifecycle orchestration and starts workers, Telegram handlers, sleep/consolidation, proxy, metrics and the optional desktop character. citeturn8view1

## Architecture status

The project has a genuine DI/layering structure, but it also retains legacy modules and compatibility paths. Documentation therefore deliberately avoids claiming that every historical module has already been migrated into a perfectly strict Clean Architecture.

## Desktop

The desktop character is a Kunipy-specific subsystem. It is currently a scaffold/stub and is intentionally isolated behind bridges and lazy imports. citeturn9view0
