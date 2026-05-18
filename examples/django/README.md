# Django Order Service

A minimal Django project (no database) that demonstrates how to integrate NirikshaAI observability into a Django application. The SDK is initialised inside `OrdersConfig.ready()` — the idiomatic place for startup side-effects — so that `opentelemetry-instrumentation-django` is applied before the first request is handled.

## Prerequisites

- Python 3.11+
- A NirikshaAI account at [app.niriksha.ai](https://app.niriksha.ai)
- A project API key (prefix `nai_`)

## Install

```bash
cd examples/django
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ../../   # install local nirikshaai SDK
```

## Run

```bash
export NIRIKSHA_API_KEY=nai_your_key_here
python manage.py runserver 8001
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/orders/` | List all orders |
| GET | `/orders/<id>/` | Fetch a single order |

Example request:

```bash
curl http://localhost:8001/orders/
curl http://localhost:8001/orders/ord-001/
```

## What you'll see in NirikshaAI

- **Traces** — Each HTTP request is captured as a trace by `opentelemetry-instrumentation-django`, with a nested `orders.list` or `orders.detail` child span carrying query attributes.
- **Logs** — Structured JSON log lines from Django and the `orders` logger are indexed and searchable.
- **Metrics** — Standard HTTP server metrics (request count, latency histogram) are exported automatically.
