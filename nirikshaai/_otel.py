"""Internal: configure OpenTelemetry SDK for NirikshaAI."""

from __future__ import annotations

import importlib
import logging
import ssl
from typing import Any

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
    "django": "opentelemetry.instrumentation.django",
    "flask": "opentelemetry.instrumentation.flask",
    "fastapi": "opentelemetry.instrumentation.fastapi",
    "starlette": "opentelemetry.instrumentation.starlette",
    "requests": "opentelemetry.instrumentation.requests",
    "urllib3": "opentelemetry.instrumentation.urllib3",
    "aiohttp": "opentelemetry.instrumentation.aiohttp_client",
    "grpc": "opentelemetry.instrumentation.grpc",
    "sqlalchemy": "opentelemetry.instrumentation.sqlalchemy",
    "psycopg2": "opentelemetry.instrumentation.psycopg2",
    "asyncpg": "opentelemetry.instrumentation.asyncpg",
    "pymongo": "opentelemetry.instrumentation.pymongo",
    "redis": "opentelemetry.instrumentation.redis",
    "celery": "opentelemetry.instrumentation.celery",
}

# LLM, agent-framework and vector-store instrumentations — only applied when
# enable_llm=True.
#
# Every entry here must also be pinned in the "llm" extra in pyproject.toml.
# An entry that is not pinned is silently never installed and so never runs:
# _try_instrument swallows the ImportError. tests/test_otel_instrumentations.py
# asserts the two lists agree, because they previously did not — llama_index,
# mistralai and google_generativeai were listed here but absent from the extra.
#
# All of these emit OTel GenAI (`gen_ai.*`) or OpenInference attributes, which
# the platform already maps to its materialized LLM columns, so adding one
# requires no server-side work.
#
# Two upstream conventions appear here. `opentelemetry.instrumentation.*` is
# OpenLLMetry (traceloop); `openinference.instrumentation.*` is OpenInference
# (Arize), used only for frameworks OpenLLMetry does not cover. Both are read by
# the platform's materialized columns, so the choice is purely about which
# project actually ships an instrumentor for a given framework.
#
# Before adding an entry, confirm the wheel really exports a class whose name
# ends in "Instrumentor" — that is what _try_instrument looks for, and it does
# nothing at all when there is none. `openinference-instrumentation-pydantic-ai`
# is the cautionary case: it exists, installs, and exports an
# OpenInferenceSpanProcessor rather than an instrumentor, so listing it here
# would have been another silently dead entry. Pydantic AI is a doc recipe
# instead — it emits OTel GenAI spans natively, so pointing it at the gateway is
# all that is needed.
_LLM_INSTRUMENTATIONS: dict[str, str] = {
    # Model providers
    "openai": "opentelemetry.instrumentation.openai",
    "anthropic": "opentelemetry.instrumentation.anthropic",
    "bedrock": "opentelemetry.instrumentation.bedrock",
    "vertexai": "opentelemetry.instrumentation.vertexai",
    "google_generativeai": "opentelemetry.instrumentation.google_generativeai",
    "mistral": "opentelemetry.instrumentation.mistralai",
    "cohere": "opentelemetry.instrumentation.cohere",
    "groq": "opentelemetry.instrumentation.groq",
    "ollama": "opentelemetry.instrumentation.ollama",
    "together": "opentelemetry.instrumentation.together",
    "replicate": "opentelemetry.instrumentation.replicate",
    "watsonx": "opentelemetry.instrumentation.watsonx",
    "sagemaker": "opentelemetry.instrumentation.sagemaker",
    "transformers": "opentelemetry.instrumentation.transformers",
    # Agent / orchestration frameworks
    "langchain": "opentelemetry.instrumentation.langchain",
    "llama_index": "opentelemetry.instrumentation.llamaindex",
    "crewai": "opentelemetry.instrumentation.crewai",
    "haystack": "opentelemetry.instrumentation.haystack",
    "mcp": "opentelemetry.instrumentation.mcp",
    "openai_agents": "opentelemetry.instrumentation.openai_agents",
    "agno": "opentelemetry.instrumentation.agno",
    # Agent frameworks covered only by OpenInference
    "autogen": "openinference.instrumentation.autogen",
    "google_adk": "openinference.instrumentation.google_adk",
    "dspy": "openinference.instrumentation.dspy",
    "smolagents": "openinference.instrumentation.smolagents",
    "guardrails": "openinference.instrumentation.guardrails",
    # Vector stores — populate the RAG retrieval columns
    "chromadb": "opentelemetry.instrumentation.chromadb",
    "pinecone": "opentelemetry.instrumentation.pinecone",
    "qdrant": "opentelemetry.instrumentation.qdrant",
    "weaviate": "opentelemetry.instrumentation.weaviate",
    "milvus": "opentelemetry.instrumentation.milvus",
}

# Instrumentors that ship inside this SDK, for frameworks with no published
# instrumentor at all. Kept in a separate dict from _LLM_INSTRUMENTATIONS on
# purpose: the pinning guard above exists because a third-party entry with no
# matching pin is never installed, and a built-in has nothing to pin. Folding
# these in would mean weakening the check that just caught three dead entries.
#
# Adding to this dict is a last resort — an upstream package is always cheaper to
# maintain. See nirikshaai/instrumentors/__init__.py.
_BUILTIN_LLM_INSTRUMENTORS: dict[str, str] = {
    # LangGraph. The langchain instrumentor traces the LCEL calls underneath a
    # graph but flattens its structure, so per-node timing, failures and loops
    # are invisible. There is no opentelemetry-instrumentation-langgraph.
    "langgraph": "nirikshaai.instrumentors.langgraph",
}


def _build_grpc_channel_credentials(
    *,
    insecure: bool,
    tls_skip_verify: bool,
    ca_cert_file: str | None,
) -> Any:
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


def _build_exporter_kwargs(
    grpc_host: str,
    headers: dict[str, str],
    use_insecure: bool,
    tls_skip_verify: bool,
    ca_cert_file: str | None,
) -> dict:
    """Build OTLP exporter keyword arguments."""
    kwargs: dict = {
        "endpoint": f"grpc://{grpc_host}",
        "headers": headers,
    }
    if use_insecure:
        kwargs["insecure"] = True
    elif tls_skip_verify:
        import grpc

        kwargs["credentials"] = grpc.ssl_channel_credentials(ssl_target_name_override="")
    elif ca_cert_file:
        import grpc

        with open(ca_cert_file, "rb") as f:
            root_certs = f.read()
        kwargs["credentials"] = grpc.ssl_channel_credentials(root_certificates=root_certs)
    return kwargs


def _build_sampler(sample_rate: float) -> Any:
    """Return an appropriate OpenTelemetry sampler for the given rate."""
    from opentelemetry.sdk.trace.sampling import (
        ALWAYS_OFF,
        ALWAYS_ON,
        ParentBased,
        TraceIdRatioBased,
    )

    if sample_rate >= 1.0:
        return ALWAYS_ON
    if sample_rate <= 0.0:
        return ALWAYS_OFF
    return ParentBased(TraceIdRatioBased(sample_rate))


def _setup_metrics(resource: Any, exporter_kwargs: dict) -> None:
    """Configure the OpenTelemetry metrics pipeline."""
    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        metric_exporter = OTLPMetricExporter(**exporter_kwargs)
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60_000)
        mp = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(mp)
        logger.debug("NirikshaAI: metrics exporter configured")
    except ImportError:
        logger.debug(
            "NirikshaAI: metrics exporter not available "
            "(install opentelemetry-exporter-otlp-proto-grpc)"
        )


def _setup_logs(resource: Any, exporter_kwargs: dict) -> None:
    """Configure the OpenTelemetry logging pipeline."""
    try:
        from opentelemetry import _logs
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        log_exporter = OTLPLogExporter(**exporter_kwargs)
        lp = LoggerProvider(resource=resource)
        lp.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        _logs.set_logger_provider(lp)

        # Attach to root logger so existing logging.getLogger(...) calls are exported.
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=lp)
        logging.getLogger().addHandler(handler)
        logger.debug("NirikshaAI: logs exporter configured")
    except ImportError:
        logger.debug("NirikshaAI: logs exporter not available")


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
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Derive gRPC address
    if otlp_endpoint:
        grpc_host = otlp_endpoint
    else:
        host = endpoint.rstrip("/").replace("https://", "").replace("http://", "")
        grpc_host = f"{host}:{otlp_port}"

    use_insecure = insecure or not endpoint.startswith("https")

    if insecure or tls_skip_verify:
        logger.warning("NirikshaAI: TLS verification disabled — do not use in production")

    headers: dict[str, str] = {"x-api-key": api_key}
    if capture_prompts:
        headers["x-capture-prompts"] = "true"

    exporter_kwargs = _build_exporter_kwargs(
        grpc_host, headers, use_insecure, tls_skip_verify, ca_cert_file
    )

    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            "deployment.environment": environment,
            "telemetry.sdk.name": "nirikshaai-python",
            "telemetry.sdk.version": sdk_version,
            "telemetry.sdk.language": "python",
        }
    )

    # ── Traces ────────────────────────────────────────────────────────────────
    sampler = _build_sampler(sample_rate)
    trace_exporter = OTLPSpanExporter(**exporter_kwargs)
    tp = TracerProvider(resource=resource, sampler=sampler)
    tp.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tp)

    # ── Metrics ───────────────────────────────────────────────────────────────
    if enable_metrics:
        _setup_metrics(resource, exporter_kwargs)

    # ── Logs ──────────────────────────────────────────────────────────────────
    if enable_logs:
        _setup_logs(resource, exporter_kwargs)

    # ── Auto-instrumentation ──────────────────────────────────────────────────
    skip = set(disable_instrumentations)
    libs_to_instrument = dict(_GENERAL_INSTRUMENTATIONS)
    if enable_llm:
        libs_to_instrument.update(_LLM_INSTRUMENTATIONS)
        libs_to_instrument.update(_BUILTIN_LLM_INSTRUMENTORS)

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
            if capture_prompts:
                # capture_content is not universal across instrumentors. Falling
                # back keeps the span flowing (without prompt bodies) instead of
                # dropping instrumentation for that library entirely.
                try:
                    instrumentor().instrument(capture_content=True)
                except TypeError:
                    logger.debug(
                        "NirikshaAI: %s does not support capture_content; "
                        "instrumenting without prompt capture",
                        lib_name,
                    )
                    instrumentor().instrument()
            else:
                instrumentor().instrument()
            logger.debug("NirikshaAI: auto-instrumented %s", lib_name)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("NirikshaAI: failed to instrument %s: %s", lib_name, exc)
