"""OpenTelemetry Baggage helpers for NirikshaAI.

Baggage entries propagate across process boundaries via W3C Baggage headers,
making them useful for carrying tenant context (org ID, user ID, experiment
tag) through an entire distributed trace without touching span attributes on
every hop.

Usage::

    token = nirikshaai.set_baggage("tenant.id", "acme-corp")
    try:
        # ... outbound HTTP calls, span creation, etc.
    finally:
        nirikshaai.detach_baggage(token)
"""

from __future__ import annotations

from opentelemetry import baggage as otel_baggage
from opentelemetry.context import attach, detach, get_current


def set_baggage(key: str, value: str) -> object:
    """Set a Baggage entry in the current context.

    Creates a *new* context with the given key/value pair added to the W3C
    Baggage and attaches it as the active context for the current thread /
    async task.

    Args:
        key:   Baggage entry name (e.g. ``"tenant.id"``).
        value: Baggage entry value.

    Returns:
        An opaque token that must be passed to :func:`detach_baggage` when the
        caller's scope ends, to restore the previous context.
    """
    ctx = otel_baggage.set_baggage(key, value, context=get_current())
    return attach(ctx)


def get_baggage(key: str) -> str:
    """Get a Baggage value from the current context.

    Args:
        key: Baggage entry name to look up.

    Returns:
        The string value, or ``""`` if the key is not present.
    """
    value = otel_baggage.get_baggage(key, context=get_current())
    if value is None:
        return ""
    return str(value)


def detach_baggage(token: object) -> None:
    """Detach a previously set Baggage entry.

    Restores the context that was active before the corresponding
    :func:`set_baggage` call.

    Args:
        token: The token returned by :func:`set_baggage`.
    """
    detach(token)  # type: ignore[arg-type]
