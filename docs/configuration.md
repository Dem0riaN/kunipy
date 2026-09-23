# Configuration

The configuration reference is `config.example.toml`, while the actual accepted settings are defined by the current configuration implementation.

The main README intentionally does not reproduce the entire configuration.

## Main areas

- LLM endpoint and generation parameters
- embeddings
- Telegram
- character
- diary
- long-term memory
- working memory
- voice transcription
- vision
- TTS
- image generation
- web search
- proxy
- metrics
- desktop character
- document processing

## Provider-dependent features

Several capabilities are optional and depend on external endpoints. A feature being implemented in the code does not mean it is available without its backend.

Never store real secrets in the repository.
