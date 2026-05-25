# Contributing to nirikshaai

Thank you for helping improve the NirikshaAI Python SDK!  
Product: [niriksha.ai](https://niriksha.ai) · Company: [sandatasystem.ai](https://sandatasystem.ai)

## Development Setup

```bash
git clone https://github.com/san-data-systems/niriksha-sdk-python
cd niriksha-sdk-python
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Available Commands

| Command | Description |
|---------|-------------|
| `pytest tests/` | Run unit tests |
| `pytest tests/ --cov=nirikshaai` | Run tests with coverage |
| `ruff check nirikshaai/` | Lint source code |
| `ruff format nirikshaai/` | Format source code |
| `mypy nirikshaai/` | Type check |

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run `ruff format nirikshaai/` before committing.

Key conventions:
- PEP 8 naming (`snake_case` functions, `PascalCase` classes)
- Full type annotations on all public functions
- `from __future__ import annotations` at top of every module
- Docstrings on all public functions and classes (Google style)
- No `print()` — use `logging.getLogger("nirikshaai.*")`

## Logging

Use the internal logger helper — **never** use `print()`:

```python
from nirikshaai._logger import get_logger
logger = get_logger("mymodule")
logger.debug("cache hit for prompt %s", name)
```

## Branch Naming

- `feat/<description>` — new features
- `fix/<description>` — bug fixes
- `chore/<description>` — maintenance
- `docs/<description>` — documentation only

## Pull Request Process

1. Branch from `main`
2. Write tests first — target 70%+ coverage on new modules
3. Run `ruff check nirikshaai/ && mypy nirikshaai/ && pytest tests/` locally
4. Update `CHANGELOG.md` under `[Unreleased]`
5. Open PR — all CI checks must pass

## Publishing

Releases are automated via [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/).  
Push a `v*` tag to trigger the release workflow.

## Reporting Issues

Security vulnerabilities: see [SECURITY.md](SECURITY.md)
