"""Internal: configure OpenTelemetry SDK for NirikshaAI."""

from __future__ import annotations

import importlib
import logging
import ssl
from typing import TYPE_CHECKING

from nirikshaai._logger import get_logger

logger = get_logger()

_QUOTA_KEYWORDS = ("ResourceExhausted", "data limit reached", "quota_exceeded")


class _QuotaWarnHandler(logging.Handler):
    """Intercepts OTEL SDK internal log records that indicate quota exceeded.

    The standard OTEL SDK emits export errors at WARNING level to the
    ``opentelemetry.*`` logger hierarchy. This handler re-emits them at
    ERROR level via the ``nirikshaai`` logger so they appear in application
    logs even when OTEL SDK internals are filtered out.
    """

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if all(kw in msg for kw in ("ResourceExhausted", "data limit reached")):
            logger.error(
                "NirikshaAI: org data quota exceeded — telemetry is being dropped. "
                "Contact your platform admin to increase the quota."
            )


_quota_handler = _QuotaWarnHandler()
logging.getLogger("opentelemetry").addHandler(_quota_handler)

# General web/infra instrumentations — auto-applied if the library is installed.
# These cover any Python service (Django, Flask, FastAPI, databases, HTTP clients).
_GENERAL_INSTRUMENTATIONS: dict[str, str] = {
    "django":      "opentelemetry.instrumentation.django",
    "flask":       "opentelemetry.instrumentation.flask",
    "fastapi":     "opentelemetry.instrumentation.fastapi",
    "starlette":   "opentelemetry.instrumentation.starlette",
    "requests":    "opentelemetry.instrumentation.requests",
    "urllib3":     "opentelemetry.instrumentation.urllib3",
    "aiohttp":     "opentelemetry.instrumentation.aiohttp_client",
    "grpc":        "opentelemetry.instrumentation.grpc",
    "sqlalchemy":  "opentelemetry.instrumentation.sqlalchemy",
    "psycopg2":    "opentelemetry.instrumentation.psycopg2",
    "asyncpg":     "opentelemetry.instrumentation.asyncpg",
    "pymongo":     "opentelemetry.instrumentation.pymongo",
    "redis":       "opentelemetry.instrumentation.redis",
    "celery":      "opentelemetry.instrumentation.celery",
}

# LLM instrumentations — only applied when enable_llm=True.
_LLM_INSTRUMENTATIONS: dict[str, str] = {
    "openai":      "opentelemetry.instrumentation.openai",
    "anthropic":   "opentelemetry.instrumentation.anthropic",
    "langchain":   "opentelemetry.instrumentation.langchain",
    "llama_index": "opentelemetry.instrumentation.llamaindex",
    "mistral":     "opentelemetry.instrumentation.mistralai",
    "google_generativeai": "opentelemetry.instrumentation.google_generativeai",
}


def _build_grpc_channel_credentials(
    *,
    insecure: bool,
    tls_skip_verify: bool,
    ca_cert_file: str | None,
):
    """Return a grpc.ChannelCredentials or None for plaintext."""
    import grpc

    if insecure:
        return None  # caller must use insecure_channel or insecure=True exporter arg

    if tls_skip_verify:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return grpc.ssl_channel_credentials()  # exporter handles skip via ssl_context below

    if ca_cert_file:
        with open(ca_cert_file, "rb") as f:
            root_certs = f.read()
        return grpc.ssl_channel_credentials(root_certificates=root_certs)

    return grpc.ssl_channel_credentials()  # system roots


def _configure_otel(
    *,
    endpoint: str,
    api_key: str,
    service_name: str,
    environment: str,
    enable_metrics: bool,
    enable_logs: bool,
    enable_llm: bool,
    capture_prompts: bool,
    otlp_port: int,
    otlp_endpoint: str | None,
    insecure: bool,
    tls_skip_verify: bool,
    ca_cert_file: str | None,
    disable_instrumentations: list[str],
    sample_rate: float = 1.0,
    sdk_version: str = "0.1.0",
) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    # Derive gRPC address
    if otlp_endpoint:
        grpc_host = otlp_endpoint
    else:
        host = endpoint.rstrip("/").replace("https://", "").replace("http://", "")
        grpc_host = f"{host}:{otlp_port}"

    use_insecure = insecure or not endpoint.startswith("https")

    if insecure or tls_skip_verify:
        logger.warning(
            "NirikshaAI: TLS verification disabled — do not use in production"
        )

    headers: dict[str, str] = {"x-api-key": api_key}
    if capture_prompts:
        headers["x-capture-prompts"] = "true"

    # Build exporter kwargs — tls_skip_verify requires a custom ssl_context
    def _exporter_kwargs() -> dict:
        kwargs: dict = {
            "endpoint": f"grpc://{grpc_host}",
            "headers": headers,
        }
        if use_insecure:
            kwargs["insecure"] = True
        elif tls_skip_verify:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            import grpc
            kwargs["credentials"] = grpc.ssl_channel_credentials(
                ssl_target_name_override=""
            )
        elif ca_cert_file:
            import grpc
            with open(ca_cert_file, "rb") as f:
                root_certs = f.read()
            kwargs["credentials"] = grpc.ssl_channel_credentials(
                root_certificates=root_certs
            )
        return kwargs

    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        "deployment.environment": environment,
        "telemetry.sdk.name": "nirikshaai-python",
        "telemetry.sdk.version": sdk_version,
        "telemetry.sdk.language": "python",
    })

    # ── Traces ────────────────────────────────────────────────────────────────
    from opentelemetry.sdk.trace.sampling import (
        TraceIdRatioBased, ParentBased, ALWAYS_ON, ALWAYS_OFF,
    )

    if sample_rate >= 1.0:
        sampler = ALWAYS_ON
    elif sample_rate <= 0.0:
        sampler = ALWAYS_OFF
    else:
        sampler = ParentBased(TraceIdRatioBased(sample_rate))

    trace_exporter = OTLPSpanExporter(**_exporter_kwargs())
    tp = TracerProvider(resource=resource, sampler=sampler)
    tp.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tp)

    # ── Metrics ───────────────────────────────────────────────────────────────
    if enable_metrics:
        try:
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry import metrics

            metric_exporter = OTLPMetricExporter(**_exporter_kwargs())
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60_000)
            mp = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(mp)
            logger.debug("NirikshaAI: metrics exporter configured")
        except ImportError:
            logger.debug("NirikshaAI: metrics exporter not available (install opentelemetry-exporter-otlp-proto-grpc)")

    # ── Logs ──────────────────────────────────────────────────────────────────
    if enable_logs:
        try:
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            from opentelemetry import _logs

            log_exporter = OTLPLogExporter(**_exporter_kwargs())
            lp = LoggerProvider(resource=resource)
            lp.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            _logs.set_logger_provider(lp)

            # Attach to root logger so existing logging.getLogger(...) calls are exported.
            handler = LoggingHandler(level=logging.NOTSET, logger_provider=lp)
            logging.getLogger().addHandler(handler)
            logger.debug("NirikshaAI: logs exporter configured")
        except ImportError:
            logger.debug("NirikshaAI: logs exporter not available")

    # ── Auto-instrumentation ──────────────────────────────────────────────────
    skip = set(disable_instrumentations)
    libs_to_instrument = dict(_GENERAL_INSTRUMENTATIONS)
    if enable_llm:
        libs_to_instrument.update(_LLM_INSTRUMENTATIONS)

    for lib_name, module_path in libs_to_instrument.items():
        if lib_name in skip:
            continue
        _try_instrument(lib_name, module_path, capture_prompts if enable_llm else False)


def _try_instrument(lib_name: str, module_path: str, capture_prompts: bool) -> None:
    try:
        mod = importlib.import_module(module_path)
        instrumentor = None
        for attr in dir(mod):
            if attr.endswith("Instrumentor"):
                instrumentor = getattr(mod, attr)
                break
        if instrumentor is not None:
            kwargs: dict = {}
            if capture_prompts:
                kwargs["capture_content"] = True
            instrumentor().instrument(**kwargs)
            logger.debug("NirikshaAI: auto-instrumented %s", lib_name)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("NirikshaAI: failed to instrument %s: %s", lib_name, exc)
