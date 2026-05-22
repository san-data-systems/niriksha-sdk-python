"""FastAPI order service example — NirikshaAI observability.

Demonstrates:
- Custom span inside a route handler
- Counter metric (orders created)
- Structured logging via Python logging
- Eval submission after an LLM call on POST /orders
"""

import logging
import os
import uuid
from typing import Any

import nirikshaai
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Initialise NirikshaAI before creating the FastAPI app so that
# opentelemetry-instrumentation-fastapi is applied automatically.
# ---------------------------------------------------------------------------
nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    otlp_endpoint="grpc-ingest.niriksha.ai:443",
    api_key=os.environ["NIRIKSHA_API_KEY"],
    service_name="order-service",
    environment=os.getenv("APP_ENV", "production"),
    enable_llm=True,
)

log = logging.getLogger("order-service")
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(title="Order Service")

# ---------------------------------------------------------------------------
# OTEL instruments
# ---------------------------------------------------------------------------
tracer = trace.get_tracer("order-service")
meter = metrics.get_meter("order-service")
orders_counter = meter.create_counter(
    "orders.created",
    unit="1",
    description="Total number of orders created",
)

# ---------------------------------------------------------------------------
# In-memory store (replace with a real DB in production)
# ---------------------------------------------------------------------------
_orders: dict[str, dict[str, Any]] = {}


class OrderRequest(BaseModel):
    customer_id: str
    items: list[str]
    note: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict[str, Any]:
    with tracer.start_as_current_span("orders.fetch") as span:
        span.set_attribute("order.id", order_id)
        order = _orders.get(order_id)
        if not order:
            log.warning("order not found", extra={"order_id": order_id})
            raise HTTPException(status_code=404, detail="Order not found")
        log.info("order fetched", extra={"order_id": order_id})
        return order


@app.post("/orders", status_code=201)
def create_order(req: OrderRequest) -> dict[str, Any]:
    with tracer.start_as_current_span("orders.create") as span:
        order_id = str(uuid.uuid4())
        span.set_attribute("order.id", order_id)
        span.set_attribute("order.customer_id", req.customer_id)
        span.set_attribute("order.item_count", len(req.items))

        # Simulate a brief LLM call to generate an order summary
        summary = f"Order #{order_id[:8]} for customer {req.customer_id}: {', '.join(req.items)}"

        # Retrieve the active trace ID for eval linkage
        ctx = span.get_span_context()
        trace_id = format(ctx.trace_id, "032x")

        # Submit faithfulness eval for the LLM-generated summary
        nirikshaai.submit_eval(
            trace_id=trace_id,
            metric_name="summary_quality",
            score=0.95,
            label="pass",
            explanation="Summary accurately reflects order contents.",
            eval_type="rule_based",
        )

        order = {
            "id": order_id,
            "customer_id": req.customer_id,
            "items": req.items,
            "summary": summary,
            "status": "pending",
        }
        _orders[order_id] = order
        orders_counter.add(1, {"customer_id": req.customer_id})
        log.info(
            "order created",
            extra={"order_id": order_id, "customer_id": req.customer_id},
        )
        return order
