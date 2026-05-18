"""AppConfig for the orders app.

NirikshaAI is initialised inside ready() so that it runs once after Django's
application registry is fully populated — the correct place for any startup
side-effects that depend on settings being loaded.
"""

import logging
import os

from django.apps import AppConfig

log = logging.getLogger("orders")


class OrdersConfig(AppConfig):
    name = "orders"
    verbose_name = "Orders"

    def ready(self) -> None:
        import nirikshaai

        api_key = os.environ.get("NIRIKSHA_API_KEY", "")
        if not api_key:
            log.warning("NIRIKSHA_API_KEY not set — observability disabled")
            return

        nirikshaai.init(
            endpoint="https://app.niriksha.ai",
            otlp_endpoint="ingest.niriksha.ai:4317",
            api_key=api_key,
            service_name="django-order-service",
            environment=os.getenv("APP_ENV", "production"),
        )
        log.info("NirikshaAI initialised")
