"""Tests for W3C Baggage context helpers."""
from __future__ import annotations

pytest = __import__("pytest")

opentelemetry = pytest.importorskip("opentelemetry", reason="opentelemetry not installed")

from nirikshaai.baggage import detach_baggage, get_baggage, set_baggage  # noqa: E402


class TestBaggage:
    def test_set_and_get(self) -> None:
        token = set_baggage("tenant-id", "acme-corp")
        assert get_baggage("tenant-id") == "acme-corp"
        detach_baggage(token)

    def test_get_missing_key_returns_empty(self) -> None:
        # get_baggage returns "" (empty string) when key is absent
        assert get_baggage("nonexistent-key-xyz") == ""

    def test_detach_restores_previous_context(self) -> None:
        token = set_baggage("env", "test")
        detach_baggage(token)
        # After detach, the value should no longer be present
        assert get_baggage("env") == ""

    def test_multiple_keys(self) -> None:
        t1 = set_baggage("user-id", "u123")
        t2 = set_baggage("request-id", "req456")
        assert get_baggage("user-id") == "u123"
        assert get_baggage("request-id") == "req456"
        detach_baggage(t2)
        detach_baggage(t1)
