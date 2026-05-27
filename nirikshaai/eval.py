"""Eval submission helpers for NirikshaAI."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from nirikshaai._logger import get_logger

logger = get_logger("eval")

_base_url: str = ""
_api_key: str = ""


def _configure(base_url: str, api_key: str) -> None:
    """Called by nirikshaai.init — sets base URL and API key."""
    global _base_url, _api_key
    _base_url = base_url.rstrip("/")
    _api_key = api_key


def submit_eval(
    trace_id: str,
    metric_name: str,
    score: float,
    *,
    label: str | None = None,
    explanation: str | None = None,
    eval_type: str = "rule_based",
    experiment_id: str | None = None,
    confidence: float | None = None,
    metadata: dict[str, str] | None = None,
    eval_time: str | None = None,
) -> dict[str, Any]:
    """Submit a single evaluation result for a trace.

    Args:
        trace_id:       The OTEL trace ID being evaluated.
        metric_name:    Evaluation metric name, e.g. "faithfulness", "toxicity".
        score:          Numeric score in [0.0, 1.0].
        label:          Optional categorical label: "pass", "fail", or "review".
        explanation:    Optional free-text explanation from the LLM judge.
        eval_type:      One of "rule_based", "llm_judge", "human".
        experiment_id:  Optional experiment group identifier.
        confidence:     Optional confidence value in [0.0, 1.0].
        metadata:       Optional arbitrary string key-value pairs.
        eval_time:      Optional ISO 8601 timestamp; omit to let the server use now().

    Returns:
        The created eval result as a dict, or an error dict.
    """
    url = f"{_base_url}/api/v1/sdk/evals"
    payload: dict[str, Any] = {
        "trace_id": trace_id,
        "metric_name": metric_name,
        "score": score,
        "eval_type": eval_type,
    }
    if label is not None:
        payload["label"] = label
    if explanation is not None:
        payload["explanation"] = explanation
    if experiment_id is not None:
        payload["experiment_id"] = experiment_id
    if confidence is not None:
        payload["confidence"] = confidence
    if metadata is not None:
        payload["metadata"] = metadata
    if eval_time is not None:
        payload["eval_time"] = eval_time
    return _post(url, payload)


def submit_evals_batch(evals: list[dict[str, Any]]) -> dict[str, Any]:
    """Submit multiple eval results in a single request.

    Each dict in ``evals`` may include any of the optional fields accepted by
    ``submit_eval``: label, explanation, eval_type, experiment_id, confidence,
    metadata, eval_time.
    """
    url = f"{_base_url}/api/v1/sdk/evals/batch"
    return _post(url, {"evals": evals})


def _assert_https_url(url: str) -> None:
    """Raise ValueError if the URL scheme is not http or https."""
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"NirikshaAI: only http/https URLs are permitted, got: {url!r}")


def _post(url: str, payload: dict) -> dict[str, Any]:
    _assert_https_url(url)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": _api_key},
        method="POST",
    )
    last_error: dict[str, Any] = {}
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                # Client errors — no point retrying
                body = exc.read().decode(errors="replace")
                logger.warning("NirikshaAI eval POST %s failed %d: %s", url, exc.code, body)
                return {"error": body, "status": exc.code}
            body = exc.read().decode(errors="replace")
            last_error = {"error": body, "status": exc.code}
            logger.debug(
                "NirikshaAI eval POST %s attempt %d failed %d, retrying",
                url, attempt, exc.code,
            )
        except urllib.error.URLError as exc:
            last_error = {"error": str(exc)}
            logger.debug(
                "NirikshaAI eval POST %s attempt %d URLError: %s, retrying",
                url, attempt, exc,
            )
        except Exception as exc:
            last_error = {"error": str(exc)}
            logger.debug(
                "NirikshaAI eval POST %s attempt %d error: %s, retrying",
                url, attempt, exc,
            )
        if attempt < 3:
            time.sleep(attempt * 0.5)

    logger.warning("NirikshaAI eval POST %s failed after 3 attempts: %s", url, last_error)
    return last_error
