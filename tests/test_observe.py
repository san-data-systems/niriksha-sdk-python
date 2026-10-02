"""observe / span / log emit the GenAI attributes the platform classifies on."""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from nirikshaai import log, observe, span, start_span


# One provider for the module: the OTel API accepts set_tracer_provider once
# per process, so every test shares this exporter and clears it.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    _EXPORTER.clear()
    return _EXPORTER


def _by_name(exporter: InMemorySpanExporter) -> dict[str, object]:
    return {s.name: s for s in exporter.get_finished_spans()}


def test_observe_makes_a_run_with_typed_children(exporter: InMemorySpanExporter) -> None:
    def agent() -> str:
        log("info", "started", {"q": "x"})
        plan = span("plan", lambda: "p", type="llm", model="gpt-4o")
        docs = span("search", lambda: ["d"], type="tool")
        return f"{plan}:{len(docs)}"

    assert observe("research-agent", agent) == "p:1"
    spans = _by_name(exporter)
    root = spans["research-agent"]
    assert root.parent is None
    assert root.attributes["niriksha.run"] is True
    assert root.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert root.attributes["gen_ai.agent.name"] == "research-agent"
    assert root.status.status_code == StatusCode.OK
    assert [e.name for e in root.events] == ["started"]
    assert root.events[0].attributes["q"] == "x"
    plan, search = spans["plan"], spans["search"]
    assert plan.parent.span_id == root.context.span_id
    assert plan.attributes["gen_ai.operation.name"] == "chat"
    assert plan.attributes["gen_ai.request.model"] == "gpt-4o"
    assert search.attributes["gen_ai.operation.name"] == "execute_tool"
    assert search.attributes["gen_ai.tool.name"] == "search"


def test_decorator_forms_and_errors(exporter: InMemorySpanExporter) -> None:
    @observe
    def bare() -> int:
        return 1

    @observe("named")
    def named() -> None:
        raise ValueError("boom")

    assert bare() == 1
    with pytest.raises(ValueError):
        named()
    spans = _by_name(exporter)
    assert spans["bare"].attributes["gen_ai.agent.name"] == "bare"
    failed = spans["named"]
    assert failed.status.status_code == StatusCode.ERROR
    assert any(e.name == "exception" for e in failed.events)


def test_async_and_block_forms(exporter: InMemorySpanExporter) -> None:
    @observe("async-agent")
    async def agent() -> str:
        with start_span("fetch", type="tool") as sp:
            sp.set_attribute("url", "https://x")
        return "ok"

    assert asyncio.run(agent()) == "ok"
    spans = _by_name(exporter)
    assert spans["async-agent"].status.status_code == StatusCode.OK
    assert spans["fetch"].attributes["gen_ai.tool.name"] == "fetch"
    assert spans["fetch"].attributes["url"] == "https://x"


def test_complex_attributes_are_json_encoded(exporter: InMemorySpanExporter) -> None:
    observe("a", lambda: None, attributes={"cfg": {"k": 1}, "tags": ["x", "y"], "skip": None})
    root = _by_name(exporter)["a"]
    assert root.attributes["cfg"] == '{"k": 1}'
    assert tuple(root.attributes["tags"]) == ("x", "y")
    assert "skip" not in root.attributes
