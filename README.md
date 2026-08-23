# NirikshaAI Python SDK

[![CI](https://github.com/san-data-systems/niriksha-sdk-python/actions/workflows/ci.yml/badge.svg)](https://github.com/san-data-systems/niriksha-sdk-python/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/nirikshaai.svg)](https://pypi.org/project/nirikshaai/)
[![Python versions](https://img.shields.io/pypi/pyversions/nirikshaai.svg)](https://pypi.org/project/nirikshaai/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

The official Python SDK for [NirikshaAI](https://nirikshaai.com) — AI-native observability for logs, metrics, traces, and LLM/agent telemetry.

Under the hood this is a thin wrapper around the [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/). It configures OTLP exporters, wires up auto-instrumentation, and exposes NirikshaAI-specific helpers (evals, prompt management). You can use the standard OTEL API at any time alongside it.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [LLM Applications](#llm-applications)
- [Configuration Reference](#configuration-reference)
- [Auto-Instrumented Libraries](#auto-instrumented-libraries)
- [Using the Standard OTEL API](#using-the-standard-otel-api)
- [Logging Integration](#logging-integration)
- [Eval Submission](#eval-submission)
- [Prompt Management](#prompt-management)
- [Framework Examples](#framework-examples)
- [Environment Variables](#environment-variables)

---

## Installation

```bash
pip install nirikshaai
```

To include automatic instrumentation for common web frameworks and infrastructure libraries (Django, Flask, FastAPI, SQLAlchemy, Redis, etc.):

```bash
pip install "nirikshaai[all]"
```

To also include automatic instrumentation for LLM libraries (OpenAI, Anthropic, LangChain, etc.):

```bash
pip install "nirikshaai[all,llm]"
```

**Minimum Python version:** 3.9

---

## Quick Start

Two lines is all it takes to start sending traces, metrics, and logs to NirikshaAI from any Python service:

```python
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    otlp_endpoint="grpc-ingest.niriksha.ai:443",  # SaaS: OTLP gateway is separate from the REST API
    api_key="nai_...",
    service_name="my-service",
)
# That's it — traces, metrics, and logs now flow to NirikshaAI
```

Your `api_key` is a project-scoped key (prefixed `nai_`). It encodes which org and project your telemetry belongs to — you do not need to pass org or project IDs separately.

---

## LLM Applications

Enable LLM instrumentation with the `enable_llm` flag. When set, the SDK automatically patches supported LLM client libraries so that every API call creates a standard OpenTelemetry span with token counts, model name, and (optionally) prompt/completion content.

```python
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="my-ai-service",
    enable_llm=True,        # Auto-instruments OpenAI, Anthropic, LangChain, etc.
    capture_prompts=False,  # Set True only if PII controls are in place
)

import openai  # auto-instrumented — every call creates an OTEL span

client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarise this document."}],
)
# A LLM span is emitted automatically — no extra code needed
```

> **Privacy note:** `capture_prompts=False` is the default. Setting it to `True` will capture the full text of prompts and completions as span attributes (`llm.input.messages` / `llm.output.messages`). Only enable this if you have appropriate data governance and PII controls in place.

---

## Configuration Reference

All parameters are passed to `nirikshaai.init()`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `endpoint` | `str` | *(required)* | NirikshaAI REST/control-plane base URL. SaaS: `https://app.niriksha.ai`. Private Cloud: `https://niriksha.internal` |
| `api_key` | `str` | *(required)* | Project-scoped API key with `nai_` prefix |
| `service_name` | `str` | `"my-service"` | Value of the `service.name` OTEL resource attribute |
| `environment` | `str` | `"production"` | Value of the `deployment.environment` OTEL resource attribute |
| `enable_metrics` | `bool` | `True` | Export OTLP metrics on a 60-second periodic interval |
| `enable_logs` | `bool` | `True` | Attach an OTLP log handler to the root Python `logging` logger |
| `enable_llm` | `bool` | `False` | Auto-instrument supported LLM client libraries (opt-in) |
| `capture_prompts` | `bool` | `False` | Capture `llm.input/output.messages` span attributes (PII risk) |
| `otlp_port` | `int` | `4317` | OTLP gRPC port. Ignored when `otlp_endpoint` is set. |
| `otlp_endpoint` | `str` | `None` | Override the gRPC OTLP address (`host:port`, no scheme). SaaS: `grpc-ingest.niriksha.ai:443` |
| `insecure` | `bool` | `False` | Send gRPC without TLS. Use when TLS is terminated at an ingress. |
| `tls_skip_verify` | `bool` | `False` | Use TLS but skip server certificate validation. Dev/staging only. |
| `ca_cert_file` | `str` | `None` | Path to a PEM CA certificate for verifying the gateway TLS cert. |
| `disable_instrumentations` | `list[str]` | `[]` | Library names to skip during auto-instrumentation (e.g. `["django"]`) |

### Private Cloud examples

```python
# TLS with trusted certificate (system roots)
nirikshaai.init(
    endpoint="https://niriksha.internal",
    otlp_endpoint="niriksha.internal:4317",
    api_key="nai_...",
)

# Custom / self-signed CA
nirikshaai.init(
    endpoint="https://niriksha.internal",
    otlp_endpoint="niriksha.internal:4317",
    api_key="nai_...",
    ca_cert_file="/etc/ssl/niriksha-ca.crt",
)

# Skip TLS verification (dev/staging only)
nirikshaai.init(
    endpoint="https://niriksha.internal",
    otlp_endpoint="niriksha.internal:4317",
    api_key="nai_...",
    tls_skip_verify=True,
)

# Plaintext gRPC (TLS terminated at ingress)
nirikshaai.init(
    endpoint="https://niriksha.internal",
    otlp_endpoint="niriksha.internal:4317",
    api_key="nai_...",
    insecure=True,
)
```

---

## Auto-Instrumented Libraries

### General (always enabled when the package is installed)

| Library | What's captured |
|---|---|
| `django` | HTTP requests and responses, middleware timing, view names |
| `flask` | Routes, request timing, status codes |
| `fastapi` | Routes, request timing, async support, response codes |
| `starlette` | Routes, middleware, ASGI lifecycle |
| `requests` | Outbound HTTP calls, method, URL, status code |
| `urllib3` | Low-level HTTP connections and retries |
| `aiohttp` | Async HTTP client calls |
| `grpc` | gRPC server and client calls, method names |
| `sqlalchemy` | SQL queries and transaction timing (values are not captured) |
| `psycopg2` | PostgreSQL query timing and operation type |
| `asyncpg` | Async PostgreSQL query timing |
| `pymongo` | MongoDB operation type, collection, database |
| `redis` | Redis command name (values are not captured) |
| `celery` | Task name, queue, execution state, retry count |

### LLM, agents and vector stores (requires `enable_llm=True`)

Installed by the `llm` extra. Each instrumentor is applied only if its library is
importable, so installing the extra in a project that uses just one of them is
harmless.

**Model providers**

| Library | What's captured |
|---|---|
| `openai` | Chat completions, embeddings, model name, token usage (prompt + completion) |
| `anthropic` | Messages API calls, model name, token usage |
| `bedrock` | AWS Bedrock invocations, model ID, token usage |
| `vertexai` | Vertex AI predictions, model name, token usage |
| `google-generativeai` | Gemini API calls, model name, token usage |
| `mistralai` | Chat completions, model name, token usage |
| `cohere` | Generate, chat and rerank calls, model name, token usage |
| `groq` | Chat completions, model name, token usage |
| `ollama` | Local model calls, model name, token usage |
| `together` | Chat and completion calls, model name, token usage |
| `replicate` | Model run calls and prediction IDs |
| `watsonx` | IBM watsonx.ai generation calls, model ID |
| `sagemaker` | SageMaker endpoint invocations |
| `transformers` | Local HuggingFace pipeline invocations |

**Agent and orchestration frameworks**

| Library | What's captured |
|---|---|
| `langchain` | Chain invocations, individual tool call spans, retrieval steps |
| `llama_index` | Query engine spans, retrieval spans, synthesiser spans |
| `crewai` | Crew and agent task execution spans |
| `haystack` | Pipeline and component spans |
| `mcp` | MCP tool calls, server name and method |

**Vector stores** — these populate the RAG retrieval views (data source, document count, top score).

| Library | What's captured |
|---|---|
| `chromadb` | Query and add operations, collection name |
| `pinecone` | Query and upsert operations, index name |
| `qdrant` | Search and upsert operations, collection name |
| `weaviate` | Query operations, class name |
| `milvus` | Search and insert operations, collection name |

---

## Using the Standard OTEL API

`nirikshaai.init()` configures the global OpenTelemetry providers. You can use the standard OTEL API directly at any point after calling `init()`:

```python
from opentelemetry import trace, metrics

tracer = trace.get_tracer("my-service")
meter  = metrics.get_meter("my-service")

# Custom span
with tracer.start_as_current_span("process-order") as span:
    span.set_attribute("order.id", order_id)
    span.set_attribute("order.total", total)
    span.set_attribute("order.currency", "USD")
    result = fulfil_order(order_id)
    span.set_attribute("order.status", result.status)

# Custom counter
order_counter = meter.create_counter(
    "orders.processed",
    description="Number of orders processed",
    unit="{order}",
)
order_counter.add(1, {"status": "success", "region": "us-east"})

# Custom histogram (useful for latency)
latency_histogram = meter.create_histogram(
    "order.processing.duration",
    description="Time to process an order",
    unit="ms",
)
latency_histogram.record(142.5, {"order_type": "express"})
```

---

## Logging Integration

When `enable_logs=True` (the default), the SDK attaches an OTLP log handler to Python's root logger. All log records emitted through the standard `logging` module are automatically exported to NirikshaAI, with trace and span IDs attached so log lines are correlated to their parent trace.

```python
import logging

logger = logging.getLogger("my-service")

# Structured extra fields are forwarded as log record attributes
logger.info("Order processed", extra={"order_id": "abc123", "amount": 99.99})
logger.warning("Inventory low", extra={"sku": "WIDGET-001", "remaining": 3})
logger.error("Payment failed", extra={"error_code": "CARD_DECLINED", "order_id": "abc123"})

# Exception info is captured automatically
try:
    process_payment(order)
except PaymentError as exc:
    logger.exception("Unhandled payment error", extra={"order_id": order.id})
```

Logs are exported in batches over OTLP gRPC to the same endpoint as traces and metrics.

---

## Eval Submission

Submit evaluation results for LLM responses. Evals are linked to a specific trace so results appear in the NirikshaAI LLM Traces view alongside the originating span.

### Single eval

```python
import nirikshaai

nirikshaai.submit_eval(
    trace_id="your-otel-trace-id",   # hex trace ID from the OTEL span context
    metric_name="faithfulness",
    score=0.92,                       # float in [0, 1]
    label="pass",                     # "pass" | "fail" | any custom label
    explanation="Response accurately reflects the source documents",
    eval_type="llm_judge",            # "llm_judge" | "rule_based" | "human"
)
```

### Batch eval

```python
nirikshaai.submit_evals_batch([
    {
        "trace_id": "abc123...",
        "metric_name": "toxicity",
        "score": 0.02,
        "label": "pass",
        "eval_type": "rule_based",
    },
    {
        "trace_id": "abc123...",
        "metric_name": "relevance",
        "score": 0.87,
        "label": "pass",
        "eval_type": "llm_judge",
        "explanation": "Response addresses the user's question directly",
    },
])
```

### Obtaining the trace ID from an active span

```python
from opentelemetry import trace

with tracer.start_as_current_span("llm-call") as span:
    ctx = span.get_span_context()
    trace_id = format(ctx.trace_id, "032x")  # 32-character hex string

    response = client.chat.completions.create(...)

    # Submit eval referencing this trace
    nirikshaai.submit_eval(
        trace_id=trace_id,
        metric_name="faithfulness",
        score=judge(response),
        label="pass",
    )
```

---

## Prompt Management

Fetch versioned prompt templates from the NirikshaAI prompt vault. Variable substitution is performed server-side before the rendered text is returned.

### Fetch the latest deployed version

```python
prompt = nirikshaai.get_prompt("customer-support-system")
print(prompt["text"])           # Rendered prompt text
print(prompt["version"])        # Active version number
print(prompt["name"])
```

### Fetch a specific version with variable substitution

```python
prompt = nirikshaai.get_prompt(
    "product-description",
    version=3,
    variables={
        "product_name": "Widget Pro",
        "category": "Electronics",
        "price": "$49.99",
    },
)
print(prompt["text"])  # All {{variables}} replaced server-side
```

### List all available prompts

```python
prompts = nirikshaai.list_prompts()
for p in prompts:
    print(f"{p['name']} (v{p['version']}) — {p['description']}")
```

---

## Framework Examples

### Django

Call `nirikshaai.init()` in your `settings.py` (or in an `AppConfig.ready()` method). Auto-instrumentation is applied globally once at startup.

```python
# myproject/settings.py
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="django-app",
    environment="production",
)

INSTALLED_APPS = [
    # ... your apps
]
```

### Flask

```python
from flask import Flask
import nirikshaai

# init() before creating the Flask app
nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="flask-app",
)

app = Flask(__name__)

@app.route("/orders/<order_id>")
def get_order(order_id):
    # This route is automatically traced — no extra code needed
    order = db.get_order(order_id)
    return {"id": order_id, "status": order.status}
```

### FastAPI

```python
from fastapi import FastAPI
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="fastapi-app",
)

app = FastAPI()

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    # Async routes are fully supported — traced automatically
    order = await db.get_order(order_id)
    return {"id": order_id, "status": order.status}
```

### Celery

```python
from celery import Celery
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="celery-worker",
)

app = Celery("tasks", broker="redis://localhost:6379/0")

@app.task
def send_notification(user_id: str, message: str):
    # Every task invocation is automatically traced
    # The task name, queue, and retry count appear as span attributes
    notify(user_id, message)
```

### LLM application with eval feedback loop

```python
import nirikshaai
from opentelemetry import trace

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    api_key="nai_...",
    service_name="rag-service",
    enable_llm=True,
)

import openai

client = openai.OpenAI()
tracer = trace.get_tracer("rag-service")

def answer_question(question: str) -> str:
    with tracer.start_as_current_span("answer-question") as span:
        span.set_attribute("question.length", len(question))

        # LLM call is auto-instrumented — a child span is created
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question},
            ],
        )
        answer = response.choices[0].message.content

        # Record trace ID for eval submission
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")

    # Async eval — run your judge independently and post the result
    score = run_faithfulness_judge(question, answer)
    nirikshaai.submit_eval(
        trace_id=trace_id,
        metric_name="faithfulness",
        score=score,
        label="pass" if score >= 0.8 else "fail",
        eval_type="llm_judge",
    )

    return answer
```

---

## Environment Variables

You can configure the SDK through standard OpenTelemetry environment variables instead of (or in addition to) passing arguments to `init()`. Environment variables take lower precedence than explicit arguments.

| Variable | Equivalent `init()` parameter |
|---|---|
| `OTEL_SERVICE_NAME` | `service_name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Derived from `endpoint` + `otlp_port` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Set to `X-API-Key=nai_your_key` |
| `OTEL_RESOURCE_ATTRIBUTES` | Use to set `deployment.environment` and other attributes |

Example shell setup:

```bash
export OTEL_SERVICE_NAME=my-service
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-nirikshaai:4317
export OTEL_EXPORTER_OTLP_HEADERS="X-API-Key=nai_your_key"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=production"
```

Then call `init()` with no arguments (the SDK will read the environment):

```python
import nirikshaai
nirikshaai.init()
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
