# Celery Worker

A Celery worker with two tasks — `send_email` and `process_payment` — that demonstrates NirikshaAI observability for async job processing. `nirikshaai.init()` is called inside `celery_app.py` before the `Celery(...)` object is constructed, which ensures that `opentelemetry-instrumentation-celery` covers every task execution from the first enqueue.

## Prerequisites

- Python 3.11+
- Redis running locally (`docker run -p 6379:6379 redis:7-alpine`)
- A NirikshaAI account at [app.niriksha.ai](https://app.niriksha.ai)
- A project API key (prefix `nai_`)

## Install

```bash
cd examples/celery
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install ../../   # install local nirikshaai SDK
```

## Run

Start the worker:

```bash
export NIRIKSHA_API_KEY=nai_your_key_here
python worker.py
```

In a second terminal, enqueue tasks:

```python
from celery_app import celery_app  # triggers nirikshaai.init()
import os; os.environ["NIRIKSHA_API_KEY"] = "nai_your_key_here"
from tasks import send_email, process_payment

send_email.delay("alice@example.com", "Welcome!", "Thanks for signing up.")
process_payment.delay("ord-123", 4999, "USD")
```

## What you'll see in NirikshaAI

- **Traces** — Each Celery task produces a trace spanning the full lifecycle (enqueue → execute → result). Custom child spans (`email.send`, `payment.process`) appear nested inside the task root span, carrying attributes like `email.recipient` and `payment.amount_cents`.
- **Logs** — Structured JSON log lines emitted inside tasks are captured and correlated with their parent trace.
- **Metrics** — Task execution counts and durations are exported as OTLP metrics.
