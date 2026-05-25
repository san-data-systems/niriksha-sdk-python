"""Tests for internal logger helper."""
from __future__ import annotations

import logging

from nirikshaai._logger import get_logger


class TestGetLogger:
    def test_returns_nirikshaai_logger(self) -> None:
        logger = get_logger()
        assert logger.name == "nirikshaai"

    def test_returns_child_logger(self) -> None:
        logger = get_logger("eval")
        assert logger.name == "nirikshaai.eval"

    def test_returns_logging_logger_instance(self) -> None:
        logger = get_logger()
        assert isinstance(logger, logging.Logger)

    def test_same_instance_for_same_name(self) -> None:
        assert get_logger("prompt") is get_logger("prompt")
