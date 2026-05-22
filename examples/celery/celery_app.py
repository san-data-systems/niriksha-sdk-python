"""Celery application factory.

Importing this module initialises NirikshaAI *before* the Celery app object is
created, ensuring that all tasks and beat schedules are covered by
opentelemetry-instrumentation-celery.

This module is imported by both tasks.py and worker.py.
"""

import logging
import os

# ---------------------------------------------------------------------------
# Step 1: initialise NirikshaAI — MUST happen before `celery.Celery(...)`.
# ---------------------------------------------------------------------------
import nirikshaai

nirikshaai.init(
    endpoint="https://app.niriksha.ai",
    otlp_endpoint="grpc-ingest.niriksha.ai:4317",
    api_key=os.environ["NIRIKSHA_API_KEY"],
    service_name="celery-worker",
    environment=os.getenv("APP_ENV", "production"),
)

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

# ---------------------------------------------------------------------------
# Step 2: create the Celery app.
# ---------------------------------------------------------------------------
from celery import Celery  # noqa: E402

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "niriksha-example",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
