"""LangGraph instrumentor.

Why this is hand-written when almost everything else is a one-line dependency:
there is **no published LangGraph instrumentor**. `opentelemetry-instrumentation-
langgraph` does not exist on PyPI, and the LangChain instrumentor — which does
cover LangGraph's underlying LCEL calls — flattens the graph. You get the LLM
calls but not the structure: no per-node attribution, no parent/child edges, and
so no way to tell which node in a graph is slow, failing, or looping.

That structure is exactly what the platform's agent views already consume.
`AgentStore.GetAgentTopology` builds a graph from parent/child spans, and
`DetectLoops` finds repeated tool calls within a trace. Both are already
implemented server-side and, until something emits per-node spans, both have
nothing to work with.

So this instrumentor emits one span per graph node, correctly parented, using
standard `gen_ai.*` attribute names. No server change is needed: the existing
materialized columns pick them up.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("nirikshaai")

# Attribute names are the OTel GenAI convention, which the platform's
# materialized columns already read. Using anything else here would require a
# schema change to get the same result.
ATTR_AGENT_NAME = "gen_ai.agent.name"
ATTR_OPERATION = "gen_ai.operation.name"
ATTR_CONVERSATION_ID = "gen_ai.conversation.id"
ATTR_TOOL_NAME = "gen_ai.tool.name"

# Node kinds, recorded as the operation name so the agent views can distinguish
# an orchestration step from a tool call.
OP_INVOKE_AGENT = "invoke_agent"
OP_EXECUTE_TOOL = "execute_tool"

# A node's own name is not always meaningful (LangGraph permits lambdas), so this
# is the fallback.
UNKNOWN_NODE = "unknown_node"


class LangGraphInstrumentor:
    """Patches LangGraph so each node execution becomes a span.

    Idempotent: calling ``instrument()`` twice is a no-op, because double
    patching would emit two spans per node and silently double every count in
    the agent views.
    """

    def __init__(self) -> None:
        self._patched: list[tuple[Any, str, Any]] = []

    # ── public API ────────────────────────────────────────────────────────────

    def instrument(self, **kwargs: Any) -> None:
        """Patch LangGraph. Accepts and ignores ``capture_content`` for symmetry
        with the upstream instrumentors, which ``_try_instrument`` may pass."""
        del kwargs  # accepted for interface compatibility

        if self._patched:
            return

        try:
            from langgraph.utils.runnable import RunnableCallable  # type: ignore
        except ImportError:
            try:
                # Older layout.
                from langgraph.utils import RunnableCallable  # type: ignore
            except ImportError:
                logger.debug(
                    "NirikshaAI: langgraph not installed or its internals moved; "
                    "skipping LangGraph instrumentation"
                )
                return

        try:
            from opentelemetry import trace
        except ImportError:
            logger.debug("NirikshaAI: opentelemetry not available; skipping LangGraph")
            return

        tracer = trace.get_tracer("nirikshaai.langgraph")
        self._patch(RunnableCallable, "invoke", tracer, is_async=False)
        self._patch(RunnableCallable, "ainvoke", tracer, is_async=True)

        if self._patched:
            logger.debug("NirikshaAI: auto-instrumented langgraph (%d hooks)", len(self._patched))

    def uninstrument(self) -> None:
        """Restore the original methods. Primarily for tests — leaving a patch
        installed across test cases makes span counts depend on test order."""
        for target, name, original in reversed(self._patched):
            setattr(target, name, original)
        self._patched.clear()

    # ── internals ─────────────────────────────────────────────────────────────

    def _patch(self, target: Any, name: str, tracer: Any, *, is_async: bool) -> None:
        original = getattr(target, name, None)
        if original is None:
            # A LangGraph version without this method; nothing to wrap.
            return

        wrapper = (
            _make_async_wrapper(original, tracer)
            if is_async
            else _make_sync_wrapper(original, tracer)
        )
        setattr(target, name, wrapper)
        self._patched.append((target, name, original))


def _node_name(runnable: Any) -> str:
    """Best-effort node name.

    LangGraph nodes may be plain functions, lambdas or class instances, so
    several attributes are tried before giving up. An unnamed node is still worth
    a span — the parent/child edge is useful even without a good label.
    """
    for attr in ("name", "__name__", "func_name"):
        value = getattr(runnable, attr, None)
        if isinstance(value, str) and value:
            return value

    func = getattr(runnable, "func", None) or getattr(runnable, "afunc", None)
    if func is not None:
        value = getattr(func, "__name__", None)
        if isinstance(value, str) and value and value != "<lambda>":
            return value

    return UNKNOWN_NODE


def _looks_like_tool(name: str) -> bool:
    """Whether a node is a tool executor rather than an orchestration step.

    LangGraph's prebuilt tool node is conventionally named ``tools``. The
    distinction matters because ``DetectLoops`` keys on tool spans, so labelling
    an orchestration node as a tool would produce phantom loops.
    """
    return name in {"tools", "tool", "tool_node", "ToolNode"}


def _conversation_id(config: Any) -> str | None:
    """Extract LangGraph's thread id, which is its conversation identity.

    Mapped to ``gen_ai.conversation.id`` so multi-turn runs group into a single
    conversation in the platform, exactly as they do for a chat SDK.
    """
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    thread = configurable.get("thread_id")
    return str(thread) if thread is not None else None


def _start_attributes(runnable: Any, config: Any) -> tuple[str, dict[str, str]]:
    name = _node_name(runnable)
    is_tool = _looks_like_tool(name)

    attrs: dict[str, str] = {
        ATTR_AGENT_NAME: name,
        ATTR_OPERATION: OP_EXECUTE_TOOL if is_tool else OP_INVOKE_AGENT,
        # Marks provenance so a support engineer can tell a hand-written
        # instrumentor's spans from an upstream package's.
        "nirikshaai.instrumentor": "langgraph",
    }
    if is_tool:
        attrs[ATTR_TOOL_NAME] = name

    conv = _conversation_id(config)
    if conv:
        attrs[ATTR_CONVERSATION_ID] = conv

    return name, attrs


def _make_sync_wrapper(original: Callable[..., Any], tracer: Any) -> Callable[..., Any]:
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        config = kwargs.get("config") or (args[1] if len(args) > 1 else None)
        name, attrs = _start_attributes(self, config)

        with tracer.start_as_current_span(f"langgraph.node.{name}", attributes=attrs) as span:
            try:
                return original(self, *args, **kwargs)
            except Exception as exc:
                # Recorded then re-raised: swallowing it would change the
                # application's behaviour, which an instrumentor must never do.
                _record_exception(span, exc)
                raise

    _copy_metadata(wrapper, original)
    return wrapper


def _make_async_wrapper(original: Callable[..., Any], tracer: Any) -> Callable[..., Any]:
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        config = kwargs.get("config") or (args[1] if len(args) > 1 else None)
        name, attrs = _start_attributes(self, config)

        with tracer.start_as_current_span(f"langgraph.node.{name}", attributes=attrs) as span:
            try:
                return await original(self, *args, **kwargs)
            except Exception as exc:
                _record_exception(span, exc)
                raise

    _copy_metadata(wrapper, original)
    return wrapper


def _record_exception(span: Any, exc: BaseException) -> None:
    """Mark a span failed, tolerating a partially-available OTel API."""
    try:
        from opentelemetry.trace import Status, StatusCode

        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception as telemetry_exc:  # pragma: no cover - defensive
        # Swallowed, because telemetry must never mask the application's own
        # error — but logged, because a silently dropped span status is
        # indistinguishable from a node that never failed.
        logger.debug("NirikshaAI: could not record node exception: %s", telemetry_exc)


def _copy_metadata(wrapper: Any, original: Any) -> None:
    """Carry over the wrapped function's identity.

    Without this, LangGraph's own introspection of node callables can behave
    differently under instrumentation — an observability library changing program
    behaviour is the worst failure mode it can have.
    """
    for attr in ("__name__", "__qualname__", "__doc__", "__module__"):
        try:
            setattr(wrapper, attr, getattr(original, attr))
        except (AttributeError, TypeError):
            pass
    wrapper.__wrapped__ = original


def instrument_langgraph(**kwargs: Any) -> LangGraphInstrumentor:
    """Convenience entry point returning the instrumentor for later removal."""
    inst = LangGraphInstrumentor()
    inst.instrument(**kwargs)
    return inst
