"""Tests for the built-in LangGraph instrumentor.

langgraph itself is not a test dependency — installing an agent framework to
test a monkey-patch would make the suite slow and version-fragile. Instead the
patch target is faked in sys.modules, and the span-emitting wrappers are driven
directly with a real OpenTelemetry tracer writing to an in-memory exporter, so
the assertions are about actual spans rather than mock calls.
"""

from __future__ import annotations

import sys
import types

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from nirikshaai.instrumentors import langgraph as lg


@pytest.fixture
def recorder():
    """A tracer whose spans can be inspected, isolated from the global provider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


# ── node naming ───────────────────────────────────────────────────────────────


def test_node_name_prefers_explicit_name() -> None:
    class Node:
        name = "planner"

    assert lg._node_name(Node()) == "planner"


def test_node_name_falls_back_to_wrapped_function() -> None:
    def retrieve_docs(state):
        return state

    class Node:
        func = retrieve_docs

    assert lg._node_name(Node()) == "retrieve_docs"


def test_node_name_ignores_lambda_names() -> None:
    """A node named "<lambda>" is worse than no name — it groups unrelated nodes."""

    class Node:
        func = staticmethod(lambda state: state)

    assert lg._node_name(Node()) == lg.UNKNOWN_NODE


def test_node_name_falls_back_when_nothing_is_named() -> None:
    class Node:
        pass

    assert lg._node_name(Node()) == lg.UNKNOWN_NODE


def test_node_name_ignores_empty_name() -> None:
    """LangGraph sets name="" in some paths; that must not become the span name."""

    class Node:
        name = ""

    assert lg._node_name(Node()) == lg.UNKNOWN_NODE


# ── tool classification ───────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["tools", "tool", "tool_node", "ToolNode"])
def test_tool_nodes_are_recognised(name: str) -> None:
    assert lg._looks_like_tool(name)


@pytest.mark.parametrize("name", ["planner", "agent", "toolsmith", "should_continue"])
def test_orchestration_nodes_are_not_tools(name: str) -> None:
    """Mislabelling an orchestration node as a tool creates phantom loops in
    the platform's loop detector, which keys on tool spans."""
    assert not lg._looks_like_tool(name)


# ── conversation id ───────────────────────────────────────────────────────────


def test_conversation_id_from_thread_id() -> None:
    config = {"configurable": {"thread_id": "abc-123"}}
    assert lg._conversation_id(config) == "abc-123"


def test_conversation_id_stringifies_non_strings() -> None:
    """LangGraph accepts any hashable thread_id; span attributes must be strings."""
    assert lg._conversation_id({"configurable": {"thread_id": 7}}) == "7"


@pytest.mark.parametrize(
    "config",
    [None, {}, "not-a-dict", {"configurable": None}, {"configurable": {}}],
)
def test_conversation_id_absent(config) -> None:
    assert lg._conversation_id(config) is None


# ── attributes ────────────────────────────────────────────────────────────────


def test_agent_node_attributes() -> None:
    class Node:
        name = "planner"

    name, attrs = lg._start_attributes(Node(), None)
    assert name == "planner"
    assert attrs[lg.ATTR_AGENT_NAME] == "planner"
    assert attrs[lg.ATTR_OPERATION] == lg.OP_INVOKE_AGENT
    assert lg.ATTR_TOOL_NAME not in attrs
    assert lg.ATTR_CONVERSATION_ID not in attrs


def test_tool_node_attributes_include_tool_name() -> None:
    class Node:
        name = "tools"

    _, attrs = lg._start_attributes(Node(), {"configurable": {"thread_id": "t1"}})
    assert attrs[lg.ATTR_OPERATION] == lg.OP_EXECUTE_TOOL
    assert attrs[lg.ATTR_TOOL_NAME] == "tools"
    assert attrs[lg.ATTR_CONVERSATION_ID] == "t1"


def test_attributes_are_all_strings() -> None:
    """A non-string attribute value makes the OTel SDK drop it with a warning."""

    class Node:
        name = "tools"

    _, attrs = lg._start_attributes(Node(), {"configurable": {"thread_id": 9}})
    assert all(isinstance(v, str) for v in attrs.values())


# ── sync wrapper ──────────────────────────────────────────────────────────────


def test_sync_wrapper_emits_a_span_and_returns_the_value(recorder) -> None:
    tracer, exporter = recorder

    def original(self, state, config=None):
        return {"answer": 42}

    wrapper = lg._make_sync_wrapper(original, tracer)

    class Node:
        name = "planner"

    assert wrapper(Node(), {"q": "?"}) == {"answer": 42}

    (span,) = exporter.get_finished_spans()
    assert span.name == "langgraph.node.planner"
    assert span.attributes[lg.ATTR_AGENT_NAME] == "planner"
    assert span.attributes["nirikshaai.instrumentor"] == "langgraph"


def test_sync_wrapper_reads_config_passed_positionally(recorder) -> None:
    """LangGraph calls invoke(input, config) positionally, so a kwargs-only
    lookup would silently lose every conversation id."""
    tracer, exporter = recorder

    def original(self, state, config=None):
        return state

    wrapper = lg._make_sync_wrapper(original, tracer)

    class Node:
        name = "planner"

    wrapper(Node(), {"q": "?"}, {"configurable": {"thread_id": "positional"}})

    (span,) = exporter.get_finished_spans()
    assert span.attributes[lg.ATTR_CONVERSATION_ID] == "positional"


def test_sync_wrapper_records_and_reraises(recorder) -> None:
    tracer, exporter = recorder

    def original(self, state, config=None):
        raise ValueError("node blew up")

    wrapper = lg._make_sync_wrapper(original, tracer)

    class Node:
        name = "planner"

    with pytest.raises(ValueError, match="node blew up"):
        wrapper(Node(), {})

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.events, "the exception should be recorded as a span event"


def test_nested_nodes_are_parented(recorder) -> None:
    """The parent/child edge is the whole point: it is what the platform's
    agent topology view is built from."""
    tracer, exporter = recorder

    class Child:
        name = "retrieve"

    class Parent:
        name = "planner"

    def child_original(self, state, config=None):
        return state

    child = lg._make_sync_wrapper(child_original, tracer)

    def parent_original(self, state, config=None):
        return child(Child(), state)

    parent = lg._make_sync_wrapper(parent_original, tracer)
    parent(Parent(), {})

    spans = {s.name: s for s in exporter.get_finished_spans()}
    inner = spans["langgraph.node.retrieve"]
    outer = spans["langgraph.node.planner"]
    assert inner.parent is not None
    assert inner.parent.span_id == outer.context.span_id
    assert inner.context.trace_id == outer.context.trace_id


# ── async wrapper ─────────────────────────────────────────────────────────────


async def test_async_wrapper_emits_a_span(recorder) -> None:
    tracer, exporter = recorder

    async def original(self, state, config=None):
        return "done"

    wrapper = lg._make_async_wrapper(original, tracer)

    class Node:
        name = "planner"

    assert await wrapper(Node(), {}) == "done"
    (span,) = exporter.get_finished_spans()
    assert span.name == "langgraph.node.planner"


async def test_async_wrapper_records_and_reraises(recorder) -> None:
    tracer, exporter = recorder

    async def original(self, state, config=None):
        raise RuntimeError("async boom")

    wrapper = lg._make_async_wrapper(original, tracer)

    class Node:
        name = "tools"

    with pytest.raises(RuntimeError, match="async boom"):
        await wrapper(Node(), {})

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR


# ── metadata preservation ─────────────────────────────────────────────────────


def test_wrapper_preserves_identity(recorder) -> None:
    """LangGraph introspects node callables; an instrumentor that changes what
    introspection sees can change program behaviour."""
    tracer, _ = recorder

    def invoke(self, state, config=None):
        """Original docstring."""
        return state

    wrapper = lg._make_sync_wrapper(invoke, tracer)
    assert wrapper.__name__ == "invoke"
    assert wrapper.__doc__ == "Original docstring."
    assert wrapper.__wrapped__ is invoke


# ── instrument / uninstrument ─────────────────────────────────────────────────


def test_instrument_is_a_noop_without_langgraph(monkeypatch) -> None:
    """The SDK instruments optimistically, so an absent framework must be quiet."""
    # A None entry in sys.modules makes the import raise ImportError, so this
    # holds whether or not langgraph happens to be installed in the environment.
    for mod in ("langgraph.utils", "langgraph.utils.runnable"):
        monkeypatch.setitem(sys.modules, mod, None)

    inst = lg.LangGraphInstrumentor()
    inst.instrument()
    assert inst._patched == []


@pytest.fixture
def fake_langgraph(monkeypatch):
    """Install a minimal stand-in for langgraph.utils.runnable.RunnableCallable."""

    class RunnableCallable:
        def __init__(self, name: str) -> None:
            self.name = name

        def invoke(self, state, config=None):
            return {"seen": self.name}

        async def ainvoke(self, state, config=None):
            return {"seen": self.name}

    pkg = types.ModuleType("langgraph")
    utils = types.ModuleType("langgraph.utils")
    runnable = types.ModuleType("langgraph.utils.runnable")
    runnable.RunnableCallable = RunnableCallable
    utils.runnable = runnable
    pkg.utils = utils

    monkeypatch.setitem(sys.modules, "langgraph", pkg)
    monkeypatch.setitem(sys.modules, "langgraph.utils", utils)
    monkeypatch.setitem(sys.modules, "langgraph.utils.runnable", runnable)
    return RunnableCallable


def test_instrument_patches_both_entry_points(fake_langgraph) -> None:
    inst = lg.LangGraphInstrumentor()
    try:
        inst.instrument()
        assert {name for _, name, _ in inst._patched} == {"invoke", "ainvoke"}
    finally:
        inst.uninstrument()


def test_instrument_is_idempotent(fake_langgraph) -> None:
    """Double patching would emit two spans per node and double every count."""
    inst = lg.LangGraphInstrumentor()
    try:
        inst.instrument()
        first = list(inst._patched)
        inst.instrument()
        assert inst._patched == first
    finally:
        inst.uninstrument()


def test_uninstrument_restores_the_originals(fake_langgraph) -> None:
    before = (fake_langgraph.invoke, fake_langgraph.ainvoke)
    inst = lg.LangGraphInstrumentor()
    inst.instrument()
    assert fake_langgraph.invoke is not before[0]
    inst.uninstrument()
    assert (fake_langgraph.invoke, fake_langgraph.ainvoke) == before
    assert inst._patched == []


def test_instrument_accepts_capture_content(fake_langgraph) -> None:
    """_try_instrument passes capture_content=True when prompt capture is on;
    raising TypeError there would drop this instrumentor entirely."""
    inst = lg.LangGraphInstrumentor()
    try:
        inst.instrument(capture_content=True)
        assert inst._patched
    finally:
        inst.uninstrument()


def test_patched_invoke_still_returns_the_original_result(fake_langgraph) -> None:
    inst = lg.LangGraphInstrumentor()
    try:
        inst.instrument()
        assert fake_langgraph("planner").invoke({}) == {"seen": "planner"}
    finally:
        inst.uninstrument()


def test_convenience_helper_returns_the_instrumentor(fake_langgraph) -> None:
    inst = lg.instrument_langgraph()
    try:
        assert isinstance(inst, lg.LangGraphInstrumentor)
        assert inst._patched
    finally:
        inst.uninstrument()
