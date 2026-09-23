# Configuration

The authoritative configuration format is the implementation in the current
source tree together with `config.example.toml`.

The README intentionally does not reproduce the full configuration file.

## Configuration areas

Depending on the current build, configuration covers areas such as:

- application/runtime settings;
- LLM/model configuration;
- Telegram;
- memory;
- proxy;
- speech and media;
- image generation;
- metrics;
- character/personality settings.

## Important

Configuration names can change as the project evolves. When documentation and
the example configuration disagree, verify the corresponding dataclass,
parser, serializer, or consumer in `src/` before using the setting.

Never commit real credentials or API tokens.
