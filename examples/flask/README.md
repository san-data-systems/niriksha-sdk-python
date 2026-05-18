# Flask Todo API

A Flask REST API for a simple todo service that demonstrates NirikshaAI observability: custom span attributes on every route, a histogram tracking request duration, and structured JSON logs — all exported automatically via OpenTelemetry.

## Prerequisites

- Python 3.11+
- A NirikshaAI account at [app.niriksha.ai](https://app.niriksha.ai)
- A project API key (prefix `nai_`)

## Install

```bash
cd examples/flask
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ../../   # install local nirikshaai SDK
```

## Run

```bash
export NIRIKSHA_API_KEY=nai_your_key_here
python app.py
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/todos` | List all todos |
| POST | `/todos` | Create a todo |
| DELETE | `/todos/<id>` | Delete a todo |

Example requests:

```bash
curl http://localhost:5000/todos

curl -X POST http://localhost:5000/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy groceries"}'

curl -X DELETE http://localhost:5000/todos/<id>
```

## What you'll see in NirikshaAI

- **Traces** — Each HTTP request produces a root Flask span plus a nested `todos.create` / `todos.list` / `todos.delete` child span. Span attributes include `todo.id` and `todo.title_length`.
- **Metrics** — The `http.server.request_duration` histogram is recorded per route and method, visible as a latency distribution on the Metrics page.
- **Logs** — JSON-formatted log lines (including `todo_id` context) are captured and indexed.
