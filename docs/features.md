# Features

This page is intentionally a feature overview. Exact implementation status is maintained in [status.md](status.md).

## Character

The character is defined through editable Markdown prompt files. Personality, identity, behaviour and appearance can be changed without modifying Python code. citeturn10view2

## Telegram

Kunipy uses `aiotdlib`/TDLib for Telegram interaction. The current client exposes messaging, chat search, history, reactions, stickers, forwarding, editing and administrative actions. citeturn13view1

## Memory

There are two related memory paths:

1. the diary/RAG system;
2. the newer hybrid long-term memory system.

The new memory system stores vectors in ChromaDB and structured data in SQLite and is wired into the memory-integrated worker. citeturn4view0turn8view0

## Multimodal interaction

The media service handles voice transcription, image input and text document extraction. The LLM message model supports OpenAI-style multimodal content. citeturn13view0turn13view2

## Generation

Image generation uses a Stable Diffusion WebUI-compatible API. TTS is exposed as an LLM tool and can generate Telegram voice messages. citeturn10view0turn10view1

## Web search

The LLM can use a web-search tool backed by Ollama's web-search API. citeturn11view3

## Monitoring

Prometheus usage metrics and an optional metrics endpoint are implemented. citeturn8view1
