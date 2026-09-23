# Features

The following capabilities are represented in the current repository. Their
exact availability depends on configuration, installed dependencies and
external services.

## Character

Kunipy contains a character/personality layer intended to maintain a
consistent AI character across interactions.

## Memory

The memory subsystem uses persistent storage and semantic retrieval. See
[memory.md](memory.md).

## Telegram

Telegram integration is present in the application architecture and requires
the corresponding credentials and dependencies.

## Web and proxy

Web/proxy functionality is implemented as an application subsystem. See
[proxy.md](proxy.md).

## Multimodal features

The repository contains components for media, speech, text-to-speech and image
generation. Individual providers are configuration-dependent.

## Metrics

Prometheus-oriented metrics are present for monitoring application activity.

## Experimental components

Not every module in the repository represents a production-ready feature.
Experimental or scaffolded components should be described as such rather than
as completed end-user functionality.
