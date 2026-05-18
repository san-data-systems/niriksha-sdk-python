# FastAPI Order Service

A minimal FastAPI order service that demonstrates full-stack observability with NirikshaAI: distributed traces (including a custom span inside each route handler), a counter metric for orders created, structured JSON logs, and an eval result submitted after a simulated LLM call on `POST /orders`.

## Prerequisites

- Python 3.11+
- A NirikshaAI account at [app.niriksha.ai](https://app.niriksha.ai)
- A project API key (prefix `nai_`)

## Install

```bash
cd examples/fastapi
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ../../   # install local nirikshaai SDK
```

## Run

```bash
export NIRIKSHA_API_KEY=nai_your_key_here
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/orders/{id}` | Fetch an order by ID |
| POST | `/orders` | Create a new order |

Example request:

```bash
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "cust-1", "items": ["widget", "gadget"]}'
```

## What you'll see in NirikshaAI

- **Traces** — Every request produces a trace with a root FastAPI span and a nested `orders.create` / `orders.fetch` child span carrying `order.id`, `customer_id`, and `item_count` attributes.
- **Metrics** — The `orders.created` counter increments on each `POST /orders`, visible on the Metrics page.
- **Logs** — Structured JSON log lines are captured and indexed for full-text search.
- **Evals** — A `summary_quality` eval record linked to the trace ID appears under GenAI > Evals.
