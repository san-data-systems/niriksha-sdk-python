"""Flask Todo API — NirikshaAI observability example.

Demonstrates:
- Custom span attributes on each route
- A histogram recording request duration
- Structured logging
"""

import logging
import os
import time
import uuid
from typing import Any

import nirikshaai
from flask import Flask, jsonify, request
from opentelemetry import metrics, trace

# ---------------------------------------------------------------------------
# Initialise NirikshaAI before creating the Flask app so that
# opentelemetry-instrumentation-flask is applied automatically.
# ---------------------------------------------------------------------------
nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    otlp_endpoint="ingest.niriksha.ai:4317",
    api_key=os.environ["NIRIKSHA_API_KEY"],
    service_name="todo-service",
    environment=os.getenv("APP_ENV", "production"),
)

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("todo-service")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# OTEL instruments
# ---------------------------------------------------------------------------
tracer = trace.get_tracer("todo-service")
meter = metrics.get_meter("todo-service")
request_duration = meter.create_histogram(
    "http.server.request_duration",
    unit="s",
    description="Duration of HTTP requests in seconds",
)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
_todos: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/todos")
def list_todos():
    start = time.perf_counter()
    with tracer.start_as_current_span("todos.list") as span:
        span.set_attribute("todos.count", len(_todos))
        log.info("listing todos")
        result = jsonify({"todos": list(_todos.values())})
    request_duration.record(
        time.perf_counter() - start,
        {"http.method": "GET", "http.route": "/todos"},
    )
    return result


@app.post("/todos")
def create_todo():
    start = time.perf_counter()
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "")).strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    with tracer.start_as_current_span("todos.create") as span:
        todo_id = str(uuid.uuid4())
        span.set_attribute("todo.id", todo_id)
        span.set_attribute("todo.title_length", len(title))
        todo = {"id": todo_id, "title": title, "done": False}
        _todos[todo_id] = todo
        log.info("todo created", extra={"todo_id": todo_id})
        result = (jsonify(todo), 201)

    request_duration.record(
        time.perf_counter() - start,
        {"http.method": "POST", "http.route": "/todos"},
    )
    return result


@app.delete("/todos/<todo_id>")
def delete_todo(todo_id: str):
    start = time.perf_counter()
    with tracer.start_as_current_span("todos.delete") as span:
        span.set_attribute("todo.id", todo_id)
        if todo_id not in _todos:
            log.warning("todo not found for delete", extra={"todo_id": todo_id})
            return jsonify({"error": "not found"}), 404
        del _todos[todo_id]
        log.info("todo deleted", extra={"todo_id": todo_id})
        result = jsonify({"deleted": todo_id})

    request_duration.record(
        time.perf_counter() - start,
        {"http.method": "DELETE", "http.route": "/todos/<todo_id>"},
    )
    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
