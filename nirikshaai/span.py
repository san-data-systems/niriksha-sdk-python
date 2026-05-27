"""Span enrichment helpers for NirikshaAI.

Provides convenience functions for attaching LLM conversation metadata,
RAG retrieval events, and tool-call events to OpenTelemetry spans.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opentelemetry import trace


def record_conversation(
    conversation_id: str,
    session_id: str = "",
    turn_index: int = 0,
    span: trace.Span | None = None,
) -> None:
    """Set conversation metadata on the current (or provided) span.

    Args:
        conversation_id: Unique identifier for the conversation / chat thread.
        session_id:      Optional session or user-session identifier.
        turn_index:      Zero-based turn counter within the conversation.
        span:            Target span. Defaults to the current active span.
    """
    target = span if span is not None else trace.get_current_span()
    target.set_attribute("llm.conversation.id", conversation_id)
    target.set_attribute("llm.session.id", session_id)
    target.set_attribute("llm.turn.index", turn_index)


@dataclass
class RAGChunk:
    """A single chunk retrieved from a RAG pipeline.

    Attributes:
        chunk_id: Unique identifier for this chunk (e.g. vector store doc ID).
        source:   Source document name, URI, or collection.
        score:    Similarity / relevance score returned by the retriever.
        content:  Optional raw text content of the chunk.
    """

    chunk_id: str
    source: str
    score: float
    content: str = field(default="")


def record_rag_chunk(
    chunk: RAGChunk,
    span: trace.Span | None = None,
) -> None:
    """Add a span event for a retrieved RAG chunk.

    Emits a ``rag.chunk.retrieved`` event on *span* (or the current active span)
    with the chunk metadata as event attributes.  ``rag.chunk.content`` is only
    included when ``chunk.content`` is non-empty to avoid bloating spans with
    large text payloads.

    Args:
        chunk: The :class:`RAGChunk` to record.
        span:  Target span. Defaults to the current active span.
    """
    target = span if span is not None else trace.get_current_span()
    attributes: dict[str, str | float] = {
        "rag.chunk.id": chunk.chunk_id,
        "rag.source": chunk.source,
        "rag.chunk.score": chunk.score,
    }
    if chunk.content:
        attributes["rag.chunk.content"] = chunk.content
    target.add_event("rag.chunk.retrieved", attributes=attributes)


@dataclass
class ToolCall:
    """An LLM tool (function) invocation.

    Attributes:
        tool_name: Name of the tool / function called by the LLM.
        call_id:   Identifier assigned to this invocation by the model.
        input:     JSON-serialised input arguments (optional).
        output:    JSON-serialised return value (optional).
    """

    tool_name: str
    call_id: str
    input: str = field(default="")
    output: str = field(default="")


def record_tool_call(
    call: ToolCall,
    span: trace.Span | None = None,
) -> None:
    """Add a span event for an LLM tool invocation.

    Emits a ``llm.tool.call`` event on *span* (or the current active span).
    ``llm.tool.input`` and ``llm.tool.output`` are only included when the
    corresponding fields on *call* are non-empty.

    Args:
        call: The :class:`ToolCall` to record.
        span: Target span. Defaults to the current active span.
    """
    target = span if span is not None else trace.get_current_span()
    attributes: dict[str, str] = {
        "llm.tool.name": call.tool_name,
        "llm.tool.call_id": call.call_id,
    }
    if call.input:
        attributes["llm.tool.input"] = call.input
    if call.output:
        attributes["llm.tool.output"] = call.output
    target.add_event("llm.tool.call", attributes=attributes)
