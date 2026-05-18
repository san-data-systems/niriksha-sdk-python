"""Celery task definitions for the NirikshaAI observability example.

nirikshaai.init() is called in worker.py before the Celery app object is
created, so all tasks are automatically traced.
"""

import logging
import time

from celery_app import celery_app
from opentelemetry import trace

log = logging.getLogger("worker")
tracer = trace.get_tracer("worker")


@celery_app.task(bind=True, name="tasks.send_email", max_retries=3)
def send_email(self, recipient: str, subject: str, body: str) -> dict:
    """Send a transactional email.

    In a real service this would call an SMTP client or email provider SDK.
    """
    with tracer.start_as_current_span("email.send") as span:
        span.set_attribute("email.recipient", recipient)
        span.set_attribute("email.subject", subject)
        log.info(
            "sending email",
            extra={"recipient": recipient, "subject": subject},
        )
        # Simulate network call
        time.sleep(0.05)
        log.info("email sent", extra={"recipient": recipient})
        return {"status": "sent", "recipient": recipient}


@celery_app.task(bind=True, name="tasks.process_payment", max_retries=3)
def process_payment(self, order_id: str, amount_cents: int, currency: str = "USD") -> dict:
    """Process a payment for an order.

    In a real service this would call a payment gateway (Stripe, Braintree, etc.)
    """
    with tracer.start_as_current_span("payment.process") as span:
        span.set_attribute("payment.order_id", order_id)
        span.set_attribute("payment.amount_cents", amount_cents)
        span.set_attribute("payment.currency", currency)
        log.info(
            "processing payment",
            extra={"order_id": order_id, "amount_cents": amount_cents},
        )
        # Simulate payment gateway latency
        time.sleep(0.1)
        log.info("payment processed", extra={"order_id": order_id})
        return {"status": "captured", "order_id": order_id, "amount_cents": amount_cents}
