"""Serverless flush decorator for NirikshaAI.

OpenTelemetry exporters buffer telemetry and flush it in background threads.
In short-lived environments (AWS Lambda, Google Cloud Functions, Azure
Functions, container jobs) the process may exit before the buffer is drained,
silently dropping spans.

:func:`with_flush` wraps a handler so that ``nirikshaai.flush()`` is always
called in a ``finally`` block — guaranteeing delivery even when the function
raises.

Usage (sync)::

    @nirikshaai.with_flush
    def handler(event, context):
        ...

Usage (async)::

    @nirikshaai.with_flush
    async def handler(event, context):
        ...
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable


def with_flush(fn: Callable) -> Callable:
    """Decorator that calls ``nirikshaai.flush()`` after the wrapped function returns.

    Works on both sync and async callables.  ``flush()`` is imported lazily
    inside the wrapper to avoid circular import issues at module load time.

    Args:
        fn: The function to wrap — typically a serverless handler.

    Returns:
        A wrapped callable with the same signature as *fn*.
    """
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            finally:
                import nirikshaai  # noqa: PLC0415 — lazy to avoid circular import
                nirikshaai.flush()

        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        finally:
            import nirikshaai  # noqa: PLC0415 — lazy to avoid circular import
            nirikshaai.flush()

    return _sync_wrapper
