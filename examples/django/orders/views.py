"""Order views — list and detail."""

import json
import logging
import uuid
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from opentelemetry import trace

log = logging.getLogger("orders")
tracer = trace.get_tracer("orders")

# In-memory store
_orders: dict[str, dict[str, Any]] = {
    "ord-001": {"id": "ord-001", "customer_id": "cust-1", "items": ["widget"], "status": "shipped"},
    "ord-002": {"id": "ord-002", "customer_id": "cust-2", "items": ["gadget", "thingamajig"], "status": "pending"},
}


@require_GET
def list_orders(request: HttpRequest) -> JsonResponse:
    """GET /orders/ — return all orders."""
    with tracer.start_as_current_span("orders.list") as span:
        span.set_attribute("orders.count", len(_orders))
        log.info("listing orders", extra={"count": len(_orders)})
        return JsonResponse({"orders": list(_orders.values())})


@require_http_methods(["GET"])
def order_detail(request: HttpRequest, order_id: str) -> JsonResponse:
    """GET /orders/<order_id>/ — return a single order."""
    with tracer.start_as_current_span("orders.detail") as span:
        span.set_attribute("order.id", order_id)
        order = _orders.get(order_id)
        if order is None:
            log.warning("order not found", extra={"order_id": order_id})
            return JsonResponse({"error": "not found"}, status=404)
        log.info("order detail fetched", extra={"order_id": order_id})
        return JsonResponse(order)
