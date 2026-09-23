# Testing

The repository contains unit, integration and architecture-oriented tests.

Run the complete suite with:

```bash
pytest
```

Useful subsets include:

```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/architecture/
```

The exact test count is deliberately not hard-coded into the README. It changes as the repository evolves.

A release check should cover:

- imports/startup;
- configuration parsing;
- LLM connectivity;
- Telegram initialization if enabled;
- memory initialization;
- optional providers enabled for the deployment;
- proxy/metrics startup where enabled;
- absence of secrets in tracked files.
