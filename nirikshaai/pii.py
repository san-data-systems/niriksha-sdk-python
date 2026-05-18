"""PII redaction utilities for NirikshaAI.

Patterns are compiled once at module import time.  Call :func:`redact_pii`
before recording any user-facing text as a span attribute or log body when
``capture_prompts=True`` is not appropriate for your compliance posture.

Supported patterns (applied in order):
    1. Email addresses        → ``[REDACTED_EMAIL]``
    2. US/CA phone numbers    → ``[REDACTED_PHONE]``
    3. US Social Security     → ``[REDACTED_SSN]``
    4. Credit card numbers    → ``[REDACTED_CC]``
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Compiled patterns — built once at import time for efficiency
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

_PHONE_RE = re.compile(
    r"(\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"
)

_SSN_RE = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)

_CC_RE = re.compile(
    r"\b(?:\d[ \-]?){13,16}\b"
)


def redact_pii(s: str) -> str:
    """Replace common PII patterns in *s* with safe placeholders.

    Applies four substitutions in a fixed, deterministic order:

    1. Email addresses are replaced with ``[REDACTED_EMAIL]``.
    2. Phone numbers (US/Canada format) are replaced with ``[REDACTED_PHONE]``.
    3. US Social Security Numbers are replaced with ``[REDACTED_SSN]``.
    4. Credit / debit card numbers (13–16 digit sequences, optional separators)
       are replaced with ``[REDACTED_CC]``.

    Args:
        s: The input string that may contain PII.

    Returns:
        A new string with all recognised PII replaced.  The original string is
        never mutated.
    """
    s = _EMAIL_RE.sub("[REDACTED_EMAIL]", s)
    s = _PHONE_RE.sub("[REDACTED_PHONE]", s)
    s = _SSN_RE.sub("[REDACTED_SSN]", s)
    s = _CC_RE.sub("[REDACTED_CC]", s)
    return s
