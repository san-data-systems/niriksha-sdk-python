# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `dev-release.yml` workflow — automatically publishes `0.x.y.devN` pre-release to PyPI on every merge to `main`
- `RELEASE.md` — comprehensive versioning, branching, and release process guide
- Internal `_logger.py` helper providing namespaced `nirikshaai.*` loggers
- `ruff` linting and formatting configuration (replaces flake8/black/isort)
- `mypy` type checking configuration
- `pytest-cov` code coverage reporting (70% minimum gate)
- Unit tests for `pii`, `logger`, `baggage`, `span`, `serverless` modules
- GitHub Actions CI pipeline: lint, type-check, test (Python 3.9/3.11/3.12), security
- GitHub Actions release workflow (PyPI trusted publisher on `v*` tags)
- CodeQL security analysis + `pip-audit` dependency vulnerability workflow
- `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- CI/PyPI/Python version badges to README

### Fixed
- ReDoS vulnerability in credit-card PII regex (replaced catastrophic backtracking pattern)
- TLS skip-verify and insecure mode now emit a `WARNING` log

## [0.2.0] - 2025-05-01

### Added
- Initial public release
- OpenTelemetry traces, metrics, and logs via OTLP/gRPC
- Auto-instrumentation for 18 libraries (Django, Flask, FastAPI, SQLAlchemy, Redis, …)
- Optional LLM instrumentation (OpenAI, Anthropic, LangChain, …)
- WSGI/ASGI middleware wrappers
- LLM span helpers: conversation tracking, RAG chunks, tool calls
- PII redaction utilities
- W3C Baggage context propagation
- Serverless flush decorator (`@with_flush`)
- Eval submission (single and batch) with retry and timeout
- Prompt vault client with configurable TTL cache
- Quota-exceeded error surfacing via logging handler

[Unreleased]: https://github.com/san-data-systems/niriksha-sdk-python/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/san-data-systems/niriksha-sdk-python/releases/tag/v0.2.0
