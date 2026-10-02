"""Wrap an agent so the platform sees it as a run.

Three calls, modelled on what a developer reaches for first:

* :func:`observe` — wraps an agent entry point in a root span. The platform
  turns that span into an **agent run**: it appears on LLM → Runs the moment
  the first child span arrives, flips to Succeeded or Failed when this span
  ends, and the health rules (long running, repeated tool, repeated error,
  no activity, possible loop) evaluate it.
* :func:`span` — a unit of work inside the run: an LLM call, a tool call, a
  retrieval or a nested agent. The ``type`` drives how the timeline draws it.
* :func:`log` — a structured line attached to the active run.

Everything is plain OpenTelemetry with the GenAI semantic conventions
(``gen_ai.operation.name``, ``gen_ai.agent.name``, ``gen_ai.tool.name``), so
the same spans are readable by any OTel backend. Nothing here needs an LLM
library to be installed.

Example::

    from nirikshaai import init, observe, span, log

    init(endpoint="https://app.niriksha.ai", api_key="nai_...", service_name="research-agent")

    @observe("research-agent")
    def run(question: str) -> str:
        log("info", "agent started", {"question": question})
        plan = span("plan", lambda: call_model(question), type="llm", model="gpt-4o")
        docs = span("search", lambda: search(plan), type="tool")
        return span("answer", lambda: call_model(docs), type="llm")
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span as OTelSpan
from opentelemetry.trace import SpanKind, Status, StatusCode

__all__ = ["observe", "span", "log", "start_span", "SpanType"]

T = TypeVar("T")

#: The kinds of work a step can be. Mapped onto ``gen_ai.operation.name``.
SpanType = str  # "llm" | "tool" | "agent" | "retrieval"

_TRACER_NAME = "nirikshaai.observe"
_OPERATION_FOR: dict[str, str] = {
    "llm": "chat",
    "tool": "execute_tool",
    "agent": "invoke_agent",
    "retrieval": "retrieval",
}
# Marks the root span of a run so the platform never has to guess from the
# absence of a parent alone.
_RUN_ATTR = "niriksha.run"


def _tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


def _attrs(values: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce attribute values to what OTel accepts (str, bool, int, float, or lists of those)."""
    out: dict[str, Any] = {}
    for k, v in (values or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, bool, int, float)):
            out[k] = v
        elif isinstance(v, (list, tuple)) and all(
            isinstance(x, (str, bool, int, float)) for x in v
        ):
            out[k] = list(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out


def _finish(sp: OTelSpan, exc: BaseException | None) -> None:
    if exc is None:
        sp.set_status(Status(StatusCode.OK))
        return
    sp.record_exception(exc)
    sp.set_status(Status(StatusCode.ERROR, str(exc)))


def _run_with_span(sp: OTelSpan, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        result = fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised
        _finish(sp, exc)
        sp.end()
        raise
    if inspect.isawaitable(result):

        async def _await() -> T:
            try:
                value = await result  # type: ignore[misc]
            except BaseException as exc:  # noqa: BLE001
                _finish(sp, exc)
                sp.end()
                raise
            _finish(sp, None)
            sp.end()
            return value  # type: ignore[no-any-return]

        return _await()  # type: ignore[return-value]
    _finish(sp, None)
    sp.end()
    return result


def observe(
    name_or_fn: str | Callable[..., T] | None = None,
    fn: Callable[..., T] | None = None,
    *,
    type: SpanType = "agent",
    attributes: dict[str, Any] | None = None,
) -> Any:
    """Wrap an agent entry point in a root span — the platform's **run**.

    Works three ways::

        observe("research-agent", lambda: agent.run())      # call
        @observe("research-agent")                           # decorator with a name
        @observe                                              # decorator, name = function name

    Async functions are awaited; the span ends when the awaitable does.
    ``attributes`` are added to the root span (``gen_ai.*`` for conventions,
    anything else as is).
    """

    def _start(name: str) -> OTelSpan:
        sp = _tracer().start_span(
            name,
            kind=SpanKind.INTERNAL,
            attributes={
                _RUN_ATTR: True,
                "gen_ai.operation.name": _OPERATION_FOR.get(type, "invoke_agent"),
                "gen_ai.agent.name": name,
                **_attrs(attributes),
            },
        )
        return sp

    def _call(name: str, target: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        sp = _start(name)
        with trace.use_span(sp, end_on_exit=False):
            return _run_with_span(sp, target, *args, **kwargs)

    # observe(name, fn)
    if isinstance(name_or_fn, str) and fn is not None:
        return _call(name_or_fn, fn)

    # @observe("name")
    if isinstance(name_or_fn, str) or name_or_fn is None:
        run_name = name_or_fn

        def decorator(target: Callable[..., T]) -> Callable[..., T]:
            final_name = str(run_name or getattr(target, "__name__", "agent"))

            @functools.wraps(target)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                return _call(final_name, target, *args, **kwargs)

            return wrapper

        return decorator

    # @observe (bare)
    target = name_or_fn
    return observe(getattr(target, "__name__", "agent"))(target)


def span(
    name: str,
    fn: Callable[..., T],
    *,
    type: SpanType = "tool",
    model: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> T:
    """Run ``fn`` inside a child span of the current run.

    ``type`` is ``"llm"``, ``"tool"``, ``"agent"`` or ``"retrieval"`` and
    becomes ``gen_ai.operation.name``; a tool span also carries
    ``gen_ai.tool.name``, an LLM span ``gen_ai.request.model`` when given.
    Exceptions are recorded on the span and re-raised.
    """
    sp = _tracer().start_span(
        name, kind=SpanKind.INTERNAL, attributes=_step_attrs(name, type, model, attributes)
    )
    with trace.use_span(sp, end_on_exit=False):
        return _run_with_span(sp, fn)


@contextmanager
def start_span(
    name: str,
    *,
    type: SpanType = "tool",
    model: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[OTelSpan]:
    """``with start_span("search", type="tool") as sp:`` — the block form of :func:`span`."""
    sp = _tracer().start_span(
        name, kind=SpanKind.INTERNAL, attributes=_step_attrs(name, type, model, attributes)
    )
    with trace.use_span(sp, end_on_exit=False):
        try:
            yield sp
        except BaseException as exc:  # noqa: BLE001
            _finish(sp, exc)
            sp.end()
            raise
        _finish(sp, None)
        sp.end()


def _step_attrs(
    name: str, type: SpanType, model: str | None, attributes: dict[str, Any] | None
) -> dict[str, Any]:
    out: dict[str, Any] = {"gen_ai.operation.name": _OPERATION_FOR.get(type, "execute_tool")}
    if type == "tool":
        out["gen_ai.tool.name"] = name
    elif type == "agent":
        out["gen_ai.agent.name"] = name
    if model:
        out["gen_ai.request.model"] = model
    out.update(_attrs(attributes))
    return out


_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def log(level: str, message: str, attributes: dict[str, Any] | None = None) -> None:
    """A structured log line attached to the active run.

    Goes through the standard :mod:`logging` module (so ``init(enable_logs=True)``
    exports it with the trace context) **and** is recorded as an event on the
    active span, so the run page shows it even when log export is off.
    """
    attrs = _attrs(attributes)
    logging.getLogger("nirikshaai.agent").log(
        _LEVELS.get(level.lower(), logging.INFO),
        message,
        extra={"niriksha_attrs": attrs} if attrs else None,
    )
    sp = trace.get_current_span()
    if sp is not None and sp.get_span_context().is_valid:
        sp.add_event(message, attributes={"log.level": level.lower(), **attrs})
