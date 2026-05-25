"""Tests for PII redaction utility."""
from __future__ import annotations

import pytest
from nirikshaai.pii import redact_pii


class TestRedactPii:
    def test_redacts_email(self) -> None:
        assert redact_pii("contact user@example.com please") == "contact [REDACTED_EMAIL] please"

    def test_redacts_phone_dashes(self) -> None:
        result = redact_pii("call 555-123-4567 now")
        assert "[REDACTED_PHONE]" in result

    def test_redacts_ssn(self) -> None:
        result = redact_pii("ssn 123-45-6789 found")
        assert "[REDACTED_SSN]" in result

    def test_redacts_credit_card(self) -> None:
        result = redact_pii("card 4111 1111 1111 1111 ok")
        assert "[REDACTED_CC]" in result

    def test_no_mutation_when_no_pii(self) -> None:
        assert redact_pii("hello world") == "hello world"

    def test_returns_new_string(self) -> None:
        original = "test@test.com"
        result = redact_pii(original)
        assert result is not original
        assert result == "[REDACTED_EMAIL]"

    def test_multiple_pii_in_one_string(self) -> None:
        result = redact_pii("user@example.com called 555-123-4567")
        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_PHONE]" in result

    @pytest.mark.parametrize("card", [
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    ])
    def test_credit_card_formats(self, card: str) -> None:
        result = redact_pii(f"card number: {card}")
        assert "[REDACTED_CC]" in result
