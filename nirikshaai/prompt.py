"""Prompt vault helpers for NirikshaAI."""

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
    global _base_url, _api_key
    _base_url = base_url.rstrip("/")
    _api_key = api_key


def get_prompt(
    name: str,
    *,
    version: int | None = None,
    variables: dict[str, str] | None = None,
) -> str:
    """Fetch and render a prompt template from NirikshaAI prompt vault.

    Args:
        name:      Prompt template name as created in the Prompt Management UI.
        version:   Specific version number, or None for the latest deployed version.
        variables: Key-value pairs to interpolate into ``{{variable}}`` placeholders.

    Returns:
        The rendered prompt string.

    Raises:
        ValueError: If the prompt is not found or the request fails.
    """
    url = f"{_base_url}/api/v1/sdk/prompts/render"
    payload: dict[str, Any] = {"name": name, "variables": variables or {}}
    if version is not None:
        payload["version"] = version

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": _api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            return result.get("data", {}).get("content", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise ValueError(f"NirikshaAI get_prompt failed {exc.code}: {body}") from exc
    except Exception as exc:
        raise ValueError(f"NirikshaAI get_prompt error: {exc}") from exc


def list_prompts() -> list[dict[str, Any]]:
    """List all prompt templates in the project (resolved from API key)."""
    url = f"{_base_url}/api/v1/sdk/prompts"
    req = urllib.request.Request(url, headers={"X-API-Key": _api_key})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            return result.get("data", {}).get("prompts", [])
    except Exception as exc:
        raise ValueError(f"NirikshaAI list_prompts error: {exc}") from exc
