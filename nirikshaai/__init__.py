"""
NirikshaAI Python SDK
=====================
Full-stack observability for any Python service — traces, metrics, and logs
sent to NirikshaAI via OpenTelemetry.

SaaS quick start::

    import nirikshaai
    nirikshaai.init(
        endpoint="https://app.niriksha.ai",
        api_key="nai_...",
    )

For SaaS, also set otlp_endpoint to the ingest host::

    nirikshaai.init(
        endpoint="https://app.niriksha.ai",
        otlp_endpoint="grpc-ingest.niriksha.ai:443",
        api_key="nai_...",
    )

Private Cloud — TLS with trusted certificate::

    nirikshaai.init(
        endpoint="https://niriksha.internal",
        otlp_endpoint="niriksha.internal:4317",
        api_key="nai_...",
    )

Private Cloud — self-signed / custom CA::

    nirikshaai.init(
        endpoint="https://niriksha.internal",
        otlp_endpoint="niriksha.internal:4317",
        api_key="nai_...",
        ca_cert_file="/etc/ssl/niriksha-ca.crt",
    )

Private Cloud — skip TLS verification (dev/staging only)::

    nirikshaai.init(
        endpoint="https://niriksha.internal",
        otlp_endpoint="niriksha.internal:4317",
        api_key="nai_...",
        tls_skip_verify=True,
    )

Private Cloud — plaintext gRPC (TLS terminated at ingress)::

    nirikshaai.init(
        endpoint="https://niriksha.internal",
        otlp_endpoint="niriksha.internal:4317",
        api_key="nai_...",
        insecure=True,
    )

The nai_xxx API key is already scoped to your project — no org or project IDs needed.

LLM auto-instrumentation (OpenAI, Anthropic, LangChain, etc.) is available
but opt-in::

    nirikshaai.init(..., enable_llm=True)
"""

from __future__ import annotations

from nirikshaai._otel import _configure_otel
from nirikshaai.baggage import detach_baggage, get_baggage, set_baggage
from nirikshaai.eval import submit_eval, submit_evals_batch
from nirikshaai.guard import (
    GuardBlocked,
    GuardError,
    Verdict,
)
from nirikshaai.guard import (
    check as guard_check,
)
from nirikshaai.guard import (
    check_batch as guard_check_batch,
)
from nirikshaai.guard import (
    check_tool as guard_check_tool,
)
from nirikshaai.middleware import NirikshaASGIMiddleware, NirikshaWSGIMiddleware
from nirikshaai.pii import redact_pii
from nirikshaai.prompt import get_prompt, list_prompts
from nirikshaai.serverless import with_flush
from nirikshaai.span import (
    RAGChunk,
    ToolCall,
    record_conversation,
    record_rag_chunk,
    record_tool_call,
)

__version__ = "0.0.1"  # keep in sync with pyproject.toml

__all__ = [
    "__version__",
    "init",
    "is_initialized",
    "flush",
    # eval
    "submit_eval",
    "submit_evals_batch",
    # prompt
    "get_prompt",
    "list_prompts",
    # span enrichment
    "record_conversation",
    "RAGChunk",
    "record_rag_chunk",
    "ToolCall",
    "record_tool_call",
    # guard — inline AI security enforcement
    "guard_check",
    "guard_check_tool",
    "guard_check_batch",
    "Verdict",
    "GuardBlocked",
    "GuardError",
    # pii
    "redact_pii",
    # baggage
    "set_baggage",
    "get_baggage",
    "detach_baggage",
    # serverless
    "with_flush",
    # middleware
    "NirikshaWSGIMiddleware",
    "NirikshaASGIMiddleware",
]

_initialized = False


# The gateway's OTLP gRPC port and its HTTP port, which is where /v1/guard lives.
_OTLP_GRPC_PORT = "4317"
_OTLP_HTTP_PORT = "4318"


def _derive_guard_url(base: str, otlp_endpoint: str | None) -> str:
    """Best-effort guard base URL, so the common cases need no extra parameter.

    The guard endpoint is served by the OTLP gateway, not the REST API, and in
    SaaS those are different hosts — so ``endpoint`` alone is not the answer.

    When ``otlp_endpoint`` is given it names the gateway, which is the right host;
    only its port and scheme need translating. The gateway's gRPC listener is
    4317 and its HTTP listener 4318, so a default deployment maps cleanly. A
    non-default port (443 behind an ingress, for example) is kept as-is, because
    guessing would be worse than reusing what the caller already configured.

    With no ``otlp_endpoint`` — the single-host Private Cloud layout — the REST
    base is also the gateway, so it is used unchanged.

    Pass ``guard_endpoint`` explicitly for anything this does not cover; getting
    it wrong shows up as a guard that logs "unreachable" on every call, which is
    loud but only after the fact.
    """
    if not otlp_endpoint:
        return base

    host = otlp_endpoint
    scheme = "https"
    if "://" in host:
        scheme, host = host.split("://", 1)
        scheme = "http" if scheme.startswith("http") and scheme != "https" else scheme

    if ":" in host:
        hostname, port = host.rsplit(":", 1)
        if port == _OTLP_GRPC_PORT:
            port = _OTLP_HTTP_PORT
            # A bare gRPC port means a direct, usually in-cluster gateway, which
            # is typically plaintext. TLS-terminated deployments set 443 and are
            # left alone by the branch above.
            scheme = "http"
        return f"{scheme}://{hostname}:{port}"

    return f"{scheme}://{host}"


def init(
    *,
    endpoint: str,
    api_key: str,
    service_name: str = "my-service",
    environment: str = "production",
    enable_metrics: bool = True,
    enable_logs: bool = True,
    enable_llm: bool = False,
    capture_prompts: bool = False,
    sample_rate: float = 1.0,
    otlp_port: int = 4317,
    otlp_endpoint: str | None = None,
    insecure: bool = False,
    tls_skip_verify: bool = False,
    ca_cert_file: str | None = None,
    disable_instrumentations: list[str] | None = None,
    guard_endpoint: str | None = None,
    guard_fail_open: str = "open",
    guard_mode: str | None = None,
) -> None:
    """Initialise NirikshaAI telemetry for this process.

    Args:
        endpoint:        NirikshaAI REST/control-plane base URL.
                         SaaS: ``"https://app.niriksha.ai"``
                         Private Cloud: ``"https://niriksha.internal"``
        api_key:         Project-scoped API key (prefix ``nai_``).
        service_name:    ``service.name`` resource attribute (default: ``"my-service"``).
        environment:     ``deployment.environment`` attribute (default: ``"production"``).
        enable_metrics:  Export OTLP metrics (default: True).
        enable_logs:     Export OTLP logs (default: True).
        enable_llm:      Auto-instrument LLM libraries (default: False).
        capture_prompts: Capture llm.input/output.messages when enable_llm=True.
                         Keep False in production unless you have PII controls.
        sample_rate:     Head-based trace sampling rate (0.0–1.0). Default: 1.0 (sample all).
                         Use 0.1 to sample ~10% of traces.
        otlp_port:       OTLP gRPC port (default 4317). Ignored when otlp_endpoint is set.
        otlp_endpoint:   Override the gRPC OTLP address (``host:port``, no scheme).
                         Use when REST API and OTLP gateway are on different hosts.
                         SaaS: ``"grpc-ingest.niriksha.ai:443"``
        insecure:        Send gRPC traffic without TLS. Use when TLS is terminated at an
                         ingress in front of the NirikshaAI gateway.
        tls_skip_verify: Use TLS but skip server certificate validation.
                         Dev/staging only — do not use in production.
        ca_cert_file:    Path to a PEM CA certificate for the gateway's TLS cert.
                         Use for private CAs.
        disable_instrumentations: Library names to skip, e.g. ``["django", "sqlalchemy"]``.
        guard_endpoint:  Base URL of the guard endpoint (the OTLP gateway's HTTP
                         listener), e.g. ``"https://ingest.niriksha.ai"``. When omitted it
                         is derived from ``otlp_endpoint`` if set, otherwise from
                         ``endpoint`` — see ``_derive_guard_url``. The guard lives on the
                         gateway, not the REST API, so in SaaS these are different hosts.
        guard_fail_open: What ``nirikshaai.guard`` does when the guard is unreachable:
                         ``"open"`` (default) allows the text through, ``"closed"`` blocks
                         everything, ``"secrets_closed"`` allows everything except
                         locally-detectable credentials. Every fall-back logs a warning and
                         increments ``guard.fail_open`` — it is never silent.
        guard_mode:      Default mode sent with every guard call: ``"monitor"`` to observe
                         what would be blocked without enforcing, or ``"block"``. Note that
                         ``monitor`` cannot lift a block your org's AIDR policy mandates.
    """
    global _initialized
    if _initialized:
        return

    from nirikshaai import eval as _eval_mod
    from nirikshaai import guard as _guard_mod
    from nirikshaai import prompt as _prompt_mod

    base = endpoint.rstrip("/")
    _eval_mod._configure(base, api_key)
    _prompt_mod._configure(base, api_key)
    _guard_mod._configure(
        guard_endpoint.rstrip("/") if guard_endpoint else _derive_guard_url(base, otlp_endpoint),
        api_key,
        guard_fail_open,
        guard_mode,
    )

    _configure_otel(
        endpoint=endpoint,
        api_key=api_key,
        service_name=service_name,
        environment=environment,
        enable_metrics=enable_metrics,
        enable_logs=enable_logs,
        enable_llm=enable_llm,
        capture_prompts=capture_prompts,
        sample_rate=sample_rate,
        otlp_port=otlp_port,
        otlp_endpoint=otlp_endpoint,
        insecure=insecure,
        tls_skip_verify=tls_skip_verify,
        ca_cert_file=ca_cert_file,
        disable_instrumentations=disable_instrumentations or [],
        sdk_version=__version__,
    )
    _initialized = True


def flush() -> None:
    """Force-flush all pending spans, metrics, and log records.
    Call before process exit in serverless / short-lived environments."""
    from opentelemetry import metrics, trace

    tp = trace.get_tracer_provider()
    if hasattr(tp, "force_flush"):
        tp.force_flush()
    mp = metrics.get_meter_provider()
    if hasattr(mp, "force_flush"):
        mp.force_flush()


def is_initialized() -> bool:
    """Return True if nirikshaai.init() has been called."""
    return _initialized
