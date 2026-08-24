"""Inline AI security guard — check text *before* it reaches the model.

The rest of this SDK is observability: it records what happened. This module is
enforcement. It calls the gateway's synchronous ``/v1/guard`` endpoint, which
returns a verdict in single-digit milliseconds, so a prompt injection can be
refused and a leaked credential stripped before the provider call is made.

Three deliberate differences from how comparable SDKs behave, each because the
obvious choice is worse:

1. **``redact`` returns the rewritten text and continues. Only ``block``
   raises.** Raising on both means a customer who asked for PII stripping gets
   their application broken instead of their data protected.

2. **Fail-open stays the default but stops being silent.** A guard outage must
   not take down the caller's application, so an unreachable server allows the
   text through — but it logs a warning and increments ``guard.fail_open`` every
   time. A silent fail-open is a security hole wearing a reliability costume:
   the control appears to work right up until it is needed.

3. **``fail_open="secrets_closed"`` is available and is the mode a security
   buyer will actually accept.** The secret patterns are embedded here, so when
   the server is unreachable, credential exfiltration is still blocked locally
   while everything else fails open.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from nirikshaai._logger import get_logger

logger = get_logger("guard")

# ── verdict actions ──────────────────────────────────────────────────────────

ACTION_ALLOW = "allow"
ACTION_TAG = "tag"
ACTION_REDACT = "redact"
ACTION_BLOCK = "block"

# ── fail-open modes ──────────────────────────────────────────────────────────

#: Allow everything when the guard is unreachable. Default.
FAIL_OPEN = "open"
#: Block everything when the guard is unreachable. Correct for a hard compliance
#: boundary, and a guaranteed outage for everyone else.
FAIL_CLOSED = "closed"
#: Allow everything except locally-detectable secrets. The only fail mode that is
#: both safe and survivable.
FAIL_SECRETS_CLOSED = "secrets_closed"

_FAIL_MODES = (FAIL_OPEN, FAIL_CLOSED, FAIL_SECRETS_CLOSED)

# Requests are bounded because this sits on the caller's critical path. A guard
# that hangs is worse than one that is absent: the absent one fails fast.
_TIMEOUT_SECONDS = 3.0

# Batch cap mirrors the server's, so an oversized batch fails here with a clear
# message rather than as a 400 from the gateway.
_MAX_BATCH = 32


class GuardError(Exception):
    """Base class for guard errors."""


# Named for what happened, not for the fact that it is an exception. "The guard
# blocked this" is the thing a caller catches and logs; GuardBlockedError reads as
# a failure of the guard rather than a decision by it, and the distinction matters
# in an incident.
class GuardBlocked(GuardError):  # noqa: N818
    """Raised when the guard's verdict is ``block``.

    Carries the verdict so a caller can log the reason, surface a message to the
    user, or record it — a bare exception would force a second guard call to find
    out what happened.
    """

    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        rules = ", ".join(f["rule"] for f in verdict.findings if "rule" in f)
        super().__init__(f"blocked by NirikshaAI guard: {rules or 'policy'}")


@dataclass
class Verdict:
    """The guard's decision about one piece of text."""

    action: str = ACTION_ALLOW
    #: Every detection, with category, severity, rule, confidence and offsets.
    findings: list[dict[str, Any]] = field(default_factory=list)
    #: Low-precision detections recorded but not acted on.
    reasons: list[str] = field(default_factory=list)
    #: The rewritten text. Populated only when ``action`` is ``redact``.
    redacted: str = ""
    risk_score: int = 0
    risk_severity: str = ""
    #: ``project`` when an operator's stored policy was applied, ``default``
    #: when the product default was. Only ``project`` is binding.
    policy_source: str = ""
    #: True when the block comes from the operator's policy rather than from rule
    #: precision alone — which also means monitor mode will not lift it.
    policy_enforced: bool = False
    #: True when the guard was unreachable and the configured fail mode decided
    #: the outcome. Never silently true: a warning is logged whenever it is set.
    failed_open: bool = False

    @property
    def blocked(self) -> bool:
        return self.action == ACTION_BLOCK

    def text_or(self, original: str) -> str:
        """Return the text safe to send: the redaction if there was one.

        Saves every caller from writing ``v.redacted or original``, which is easy
        to get wrong in the direction that forwards the secret.
        """
        return self.redacted if self.action == ACTION_REDACT and self.redacted else original


# ── module configuration, set by nirikshaai.init ─────────────────────────────

_guard_url: str = ""
_api_key: str = ""
_fail_mode: str = FAIL_OPEN
_mode: str | None = None


def _configure(
    guard_url: str,
    api_key: str,
    fail_mode: str = FAIL_OPEN,
    mode: str | None = None,
) -> None:
    """Called by nirikshaai.init."""
    global _guard_url, _api_key, _fail_mode, _mode
    if fail_mode not in _FAIL_MODES:
        raise ValueError(
            f"NirikshaAI: guard_fail_open must be one of {_FAIL_MODES}, got {fail_mode!r}"
        )
    _guard_url = guard_url.rstrip("/")
    _api_key = api_key
    _fail_mode = fail_mode
    _mode = mode


def configured() -> bool:
    """Whether the guard has a URL to call.

    Public so a caller can branch instead of discovering the guard is inert only
    from a log line.
    """
    return bool(_guard_url and _api_key)


# ── public API ───────────────────────────────────────────────────────────────


def check(
    text: str,
    *,
    direction: str = "input",
    raise_on_block: bool = True,
) -> Verdict:
    """Evaluate one prompt or completion.

    Args:
        text: The text to check.
        direction: ``"input"`` for a prompt heading to the model, ``"output"``
            for a completion coming back. Injection and jailbreak rules apply to
            input only; secrets and PII to both.
        raise_on_block: Raise :class:`GuardBlocked` on a ``block`` verdict.
            Set False to handle the verdict yourself.

    Returns:
        A :class:`Verdict`. On ``redact``, use ``verdict.text_or(text)`` to get
        the text that is safe to send.

    Raises:
        GuardBlocked: when the verdict is ``block`` and ``raise_on_block``.
    """
    v = _evaluate({"text": text, "direction": direction}, text)
    if v.blocked and raise_on_block:
        raise GuardBlocked(v)
    return v


def check_tool(
    name: str,
    arguments: Any = None,
    *,
    raise_on_block: bool = True,
) -> Verdict:
    """Evaluate a tool call before executing it.

    This is the check that can actually prevent an action — an ``rm -rf``, an
    unscoped ``DELETE``, a credential read, an outbound request carrying a key.
    Observing the tool call afterwards cannot.

    Args:
        name: The tool being invoked.
        arguments: The arguments, as a dict/list (serialised to JSON) or a
            pre-serialised string.
        raise_on_block: Raise :class:`GuardBlocked` on a ``block`` verdict.
    """
    if arguments is None:
        args_json: Any = ""
    elif isinstance(arguments, str):
        args_json = arguments
    else:
        args_json = json.dumps(arguments)

    payload = {"tool": {"name": name, "arguments": args_json}}
    # Fallback text for the secrets-closed local check: a credential passed to an
    # outbound tool is the concrete exfiltration path, so the arguments are
    # exactly what must still be inspected when the server is unreachable.
    v = _evaluate(payload, f"{name}\n{args_json}")
    if v.blocked and raise_on_block:
        raise GuardBlocked(v)
    return v


def check_batch(
    items: list[dict[str, str]],
    *,
    raise_on_block: bool = True,
) -> tuple[str, list[Verdict]]:
    """Evaluate a whole message array in one request.

    A per-string API is an N+1 for a multi-turn conversation, which is every real
    chat application.

    Args:
        items: Up to 32 dicts of ``{"text": …, "direction": …}``.
        raise_on_block: Raise :class:`GuardBlocked` when the aggregate is
            ``block``.

    Returns:
        ``(aggregate_action, per_item_verdicts)``. The aggregate is the most
        severe of the set: one blocked message means the conversation must not be
        sent.
    """
    if not items:
        raise ValueError("NirikshaAI: guard.check_batch requires at least one item")
    if len(items) > _MAX_BATCH:
        raise ValueError(
            f"NirikshaAI: guard.check_batch accepts at most {_MAX_BATCH} items, got {len(items)}"
        )

    if not configured():
        verdicts = [_fail(item.get("text", "")) for item in items]
        return _worst(verdicts), verdicts

    payload: dict[str, Any] = {"items": items}
    if _mode:
        for item in payload["items"]:
            item.setdefault("mode", _mode)

    body = _post(f"{_guard_url}/v1/guard/batch", payload)
    if body is None:
        verdicts = [_fail(item.get("text", "")) for item in items]
        return _worst(verdicts), verdicts

    results = body.get("results") or []
    verdicts = [_verdict_from(r) for r in results]
    action = str(body.get("action") or _worst(verdicts))
    if action == ACTION_BLOCK and raise_on_block:
        blocking = next((v for v in verdicts if v.blocked), Verdict(action=ACTION_BLOCK))
        raise GuardBlocked(blocking)
    return action, verdicts


# ── internals ────────────────────────────────────────────────────────────────


def _evaluate(payload: dict[str, Any], fallback_text: str) -> Verdict:
    if not configured():
        return _fail(fallback_text)
    if _mode:
        payload = {**payload, "mode": _mode}
    body = _post(f"{_guard_url}/v1/guard", payload)
    if body is None:
        return _fail(fallback_text)
    return _verdict_from(body)


def _verdict_from(body: dict[str, Any]) -> Verdict:
    return Verdict(
        action=str(body.get("action") or ACTION_ALLOW),
        findings=list(body.get("findings") or []),
        reasons=list(body.get("reasons") or []),
        redacted=str(body.get("redacted") or ""),
        risk_score=int(body.get("risk_score") or 0),
        risk_severity=str(body.get("risk_severity") or ""),
        policy_source=str(body.get("policy_source") or ""),
        policy_enforced=bool(body.get("policy_enforced")),
    )


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST to the guard. Returns None when the guard could not be consulted.

    Deliberately no retry loop. This is a synchronous call in front of the
    caller's LLM request: retrying turns a 3-second timeout into a 9-second one,
    and the fail mode is a better answer than a slower one.
    """
    if not url.startswith(("https://", "http://")):
        logger.warning("NirikshaAI guard: refusing non-http(s) URL %r", url)
        return None

    data = json.dumps(payload).encode()
    req = urllib.request.Request(  # noqa: S310 — scheme checked above
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": _api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            parsed = json.loads(resp.read())
            if isinstance(parsed, dict):
                return parsed
            logger.warning("NirikshaAI guard: unexpected response shape from %s", url)
            return None
    except urllib.error.HTTPError as exc:
        # 4xx is a client bug — a bad key, a malformed body — and is worth
        # surfacing loudly, because it means the guard has never worked rather
        # than that it is briefly down.
        level = logger.error if exc.code < 500 else logger.warning
        level("NirikshaAI guard: %s returned %d", url, exc.code)
        return None
    except Exception as exc:
        logger.warning("NirikshaAI guard: %s unreachable (%s)", url, exc)
        return None


def _fail(text: str) -> Verdict:
    """Apply the configured fail mode.

    Never silent. Every fail-open trip logs and is countable, because a security
    control that quietly stops working is worse than one that was never
    installed — the second is at least known to be absent.
    """
    _count_fail_open()

    if _fail_mode == FAIL_CLOSED:
        logger.warning("NirikshaAI guard: unreachable and fail mode is closed — blocking")
        return Verdict(action=ACTION_BLOCK, failed_open=True)

    if _fail_mode == FAIL_SECRETS_CLOSED:
        findings = _local_secret_findings(text)
        if findings:
            logger.warning(
                "NirikshaAI guard: unreachable; blocking locally on %d secret pattern(s)",
                len(findings),
            )
            return Verdict(action=ACTION_BLOCK, findings=findings, failed_open=True)

    logger.warning(
        "NirikshaAI guard: unreachable — allowing text through (fail mode %r). "
        "Text is NOT being checked.",
        _fail_mode,
    )
    return Verdict(action=ACTION_ALLOW, failed_open=True)


def _count_fail_open() -> None:
    """Increment guard.fail_open, if a meter is available.

    Wrapped because the counter is a diagnostic: failing to record it must never
    turn a guard outage into an application crash.
    """
    try:
        from opentelemetry import metrics

        metrics.get_meter("nirikshaai.guard").create_counter(
            "guard.fail_open",
            description="Guard calls that could not reach the server",
        ).add(1, {"fail_mode": _fail_mode})
    except Exception:  # pragma: no cover - defensive
        logger.debug("NirikshaAI guard: could not record the fail_open counter")


def _worst(verdicts: list[Verdict]) -> str:
    rank = {ACTION_ALLOW: 0, ACTION_TAG: 1, ACTION_REDACT: 2, ACTION_BLOCK: 3}
    worst = ACTION_ALLOW
    for v in verdicts:
        if rank.get(v.action, 0) > rank.get(worst, 0):
            worst = v.action
    return worst


# ── local secret patterns, for fail_open="secrets_closed" ────────────────────
#
# A deliberately small, prefix-anchored subset of the server's set. The point is
# not parity — the server has eighteen patterns, entropy gating and a placeholder
# denylist — but that the highest-confidence, zero-false-positive formats are
# still caught with no network call. Every one of these is a vendor's own key
# prefix, so a match is near-certain and a non-match is cheap.

_LOCAL_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_secret_key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
    ),
    ("niriksha_api_key", re.compile(r"\bnai_(?:plat_)?[A-Za-z0-9]{20,}\b")),
)

# Documentation values that match a real pattern. Without this the local check
# would block on a README, and the first person it inconveniences would switch
# the mode off.
_LOCAL_PLACEHOLDERS = frozenset(
    {
        "akiaiosfodnn7example",
        "aws_access_key_id",
    }
)


def _local_secret_findings(text: str) -> list[dict[str, Any]]:
    """Detect embedded secret formats without calling the server."""
    if not text:
        return []
    findings: list[dict[str, Any]] = []
    for name, pattern in _LOCAL_SECRETS:
        for match in pattern.finditer(text):
            if match.group(0).lower() in _LOCAL_PLACEHOLDERS:
                continue
            findings.append(
                {
                    "category": "secret",
                    "severity": "critical",
                    "rule": name,
                    "confidence": 0.95,
                    "start": match.start(),
                    "end": match.end(),
                    "local": True,
                }
            )
    return findings
