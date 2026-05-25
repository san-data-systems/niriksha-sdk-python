"""Tests for serverless flush decorator."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestWithFlush:
    def test_sync_handler_returns_result(self) -> None:
        with patch("nirikshaai.flush") as mock_flush:
            from nirikshaai.serverless import with_flush

            @with_flush
            def handler(event: dict, context: object) -> str:
                return "ok"

            result = handler({}, None)
            assert result == "ok"
            mock_flush.assert_called_once()

    def test_flush_called_on_exception(self) -> None:
        with patch("nirikshaai.flush") as mock_flush:
            from nirikshaai.serverless import with_flush

            @with_flush
            def failing_handler(event: dict, context: object) -> None:
                raise ValueError("boom")

            with pytest.raises(ValueError, match="boom"):
                failing_handler({}, None)
            mock_flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_handler_returns_result(self) -> None:
        with patch("nirikshaai.flush") as mock_flush:
            from nirikshaai.serverless import with_flush

            @with_flush
            async def async_handler(event: dict, context: object) -> str:
                return "async-ok"

            result = await async_handler({}, None)
            assert result == "async-ok"
            mock_flush.assert_called_once()
