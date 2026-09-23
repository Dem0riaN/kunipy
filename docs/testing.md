# Testing

## Declared test tooling

`pyproject.toml` configures pytest with automatic asyncio support.

Development dependencies include:

- `pytest`
- `pytest-asyncio`
- `httpx`
- `ruff`

The repository also contains test-related architectural and integration
material.

## What this documentation claims

This document deliberately does **not** claim a precise test count or coverage
percentage.

The old README stated "50+ tests", but that number was not independently
validated during the documentation audit.

Likewise, this audit did not execute the complete test suite against a local
checkout because the repository was inspected remotely.

## Recommended local verification

After checking out the repository:

```bash
pytest
```

For the suites described by the existing repository documentation:

```bash
pytest tests/integration/
pytest tests/unit/
pytest tests/architecture/
```

And for coverage:

```bash
pytest --cov=src --cov-report=html
```

The actual test tree should be treated as authoritative if it differs from
historical README text.
