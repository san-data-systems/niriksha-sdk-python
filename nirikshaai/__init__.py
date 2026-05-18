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
        otlp_endpoint="ingest.niriksha.ai:4317",
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
from nirikshaai.eval import submit_eval, submit_evals_batch
from nirikshaai.prompt import get_prompt, list_prompts

__all__ = [
    "init",
    "submit_eval",
    "submit_evals_batch",
    "get_prompt",
    "list_prompts",
]

_initialized = False


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
    otlp_port: int = 4317,
    otlp_endpoint: str | None = None,
    insecure: bool = False,
    tls_skip_verify: bool = False,
    ca_cert_file: str | None = None,
    disable_instrumentations: list[str] | None = None,
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
        otlp_port:       OTLP gRPC port (default 4317). Ignored when otlp_endpoint is set.
        otlp_endpoint:   Override the gRPC OTLP address (``host:port``, no scheme).
                         Use when REST API and OTLP gateway are on different hosts.
                         SaaS: ``"ingest.niriksha.ai:4317"``
        insecure:        Send gRPC traffic without TLS. Use when TLS is terminated at an
                         ingress in front of the NirikshaAI gateway.
        tls_skip_verify: Use TLS but skip server certificate validation.
                         Dev/staging only — do not use in production.
        ca_cert_file:    Path to a PEM CA certificate for the gateway's TLS cert.
                         Use for private CAs.
        disable_instrumentations: Library names to skip, e.g. ``["django", "sqlalchemy"]``.
    """
    global _initialized
    if _initialized:
        return

    from nirikshaai import eval as _eval_mod, prompt as _prompt_mod
    base = endpoint.rstrip("/")
    _eval_mod._configure(base, api_key)
    _prompt_mod._configure(base, api_key)

    _configure_otel(
        endpoint=endpoint,
        api_key=api_key,
        service_name=service_name,
        environment=environment,
        enable_metrics=enable_metrics,
        enable_logs=enable_logs,
        enable_llm=enable_llm,
        capture_prompts=capture_prompts,
        otlp_port=otlp_port,
        otlp_endpoint=otlp_endpoint,
        insecure=insecure,
        tls_skip_verify=tls_skip_verify,
        ca_cert_file=ca_cert_file,
        disable_instrumentations=disable_instrumentations or [],
    )
    _initialized = True
