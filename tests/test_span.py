"""Tests for span enrichment helpers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

opentelemetry = pytest.importorskip("opentelemetry", reason="opentelemetry not installed")

from nirikshaai.span import RAGChunk, ToolCall, record_conversation, record_rag_chunk, record_tool_call  # noqa: E402


class TestRecordConversation:
    def test_no_op_when_no_active_span(self) -> None:
        # Should not raise even without an active span
        record_conversation("conv-123")

    def test_sets_attributes_on_mock_span(self) -> None:
        mock_span = MagicMock()
        record_conversation("conv-abc", session_id="sess-1", turn_index=2, span=mock_span)
        mock_span.set_attribute.assert_any_call("llm.conversation.id", "conv-abc")
        mock_span.set_attribute.assert_any_call("llm.session.id", "sess-1")
        mock_span.set_attribute.assert_any_call("llm.turn.index", 2)


class TestRecordRagChunk:
    def test_no_op_when_no_active_span(self) -> None:
        chunk = RAGChunk(chunk_id="c1", source="docs", score=0.95)
        record_rag_chunk(chunk)  # Should not raise

    def test_adds_event_on_mock_span(self) -> None:
        mock_span = MagicMock()
        chunk = RAGChunk(chunk_id="c1", source="wiki", score=0.9, content="some text")
        record_rag_chunk(chunk, span=mock_span)
        mock_span.add_event.assert_called_once()
        call_args = mock_span.add_event.call_args
        assert call_args[0][0] == "rag.chunk.retrieved"


class TestRecordToolCall:
    def test_no_op_when_no_active_span(self) -> None:
        call = ToolCall(tool_name="search", call_id="t1")
        record_tool_call(call)  # Should not raise

    def test_adds_event_on_mock_span(self) -> None:
        mock_span = MagicMock()
        call = ToolCall(tool_name="calculator", call_id="t2", input="2+2", output="4")
        record_tool_call(call, span=mock_span)
        mock_span.add_event.assert_called_once()
        call_args = mock_span.add_event.call_args
        assert call_args[0][0] == "llm.tool.call"
