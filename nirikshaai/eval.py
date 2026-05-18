"""Eval submission helpers for NirikshaAI."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("nirikshaai")

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
) -> dict[str, Any]:
    """Submit a single evaluation result for a trace.

    Args:
        trace_id:     The OTEL trace ID being evaluated.
        metric_name:  Evaluation metric name, e.g. "faithfulness", "toxicity".
        score:        Numeric score in [0.0, 1.0].
        label:        Optional categorical label: "pass", "fail", or "review".
        explanation:  Optional free-text explanation from the LLM judge.
        eval_type:    One of "rule_based", "llm_judge", "human".

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
    if label:
        payload["label"] = label
    if explanation:
        payload["explanation"] = explanation
    return _post(url, payload)


def submit_evals_batch(evals: list[dict[str, Any]]) -> dict[str, Any]:
    """Submit multiple eval results in a single request."""
    url = f"{_base_url}/api/v1/sdk/evals/batch"
    return _post(url, {"evals": evals})


def _post(url: str, payload: dict) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": _api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.warning("NirikshaAI eval POST %s failed %d: %s", url, exc.code, body)
        return {"error": body, "status": exc.code}
    except Exception as exc:
        logger.warning("NirikshaAI eval POST %s error: %s", url, exc)
        return {"error": str(exc)}
