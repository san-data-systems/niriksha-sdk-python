"""Prompt vault helpers for NirikshaAI."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from nirikshaai._logger import get_logger

logger = get_logger("prompt")

_base_url: str = ""
_api_key: str = ""

# In-memory prompt cache: cache_key → (response_dict, expiry_timestamp)
_prompt_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 300  # 5 minutes default


def _cache_key(name: str, version: int | None, variables: dict[str, str] | None) -> str:
    return f"{name}:{version}:{json.dumps(variables or {}, sort_keys=True)}"


def _configure(base_url: str, api_key: str) -> None:
    global _base_url, _api_key
    _base_url = base_url.rstrip("/")
    _api_key = api_key


def _assert_https_url(url: str) -> None:
    """Raise ValueError if the URL scheme is not http or https."""
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"NirikshaAI: only http/https URLs are permitted, got: {url!r}")


def _post_once(url: str, payload: dict) -> dict[str, Any]:
    """Send a single POST request; returns the parsed response dict."""
    req = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": _api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def _get_once(url: str) -> dict[str, Any]:
    """Send a single GET request; returns the parsed response dict."""
    req = urllib.request.Request(url, headers={"X-API-Key": _api_key})  # noqa: S310
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def get_prompt(
    name: str,
    *,
    version: int | None = None,
    variables: dict[str, str] | None = None,
    cache_ttl: int = 300,
) -> dict[str, Any]:
    """Fetch and render a prompt template from NirikshaAI prompt vault.

    Args:
        name:       Prompt template name as created in the Prompt Management UI.
        version:    Specific version number, or None for the latest deployed version.
        variables:  Key-value pairs to interpolate into ``{{variable}}`` placeholders.
        cache_ttl:  Cache TTL in seconds (default: 300). Set to 0 to bypass cache.

    Returns:
        A dict with at minimum ``content`` (rendered prompt string) and optional
        fields ``created_at``, ``updated_at``, ``tags``.

    Raises:
        ValueError: If the prompt is not found or the request fails after retries.
    """
    key = _cache_key(name, version, variables)
    if cache_ttl > 0:
        cached = _prompt_cache.get(key)
        if cached is not None and time.time() < cached[1]:
            logger.debug("NirikshaAI get_prompt cache hit for %r", name)
            return cached[0]

    url = f"{_base_url}/api/v1/sdk/prompts/render"
    _assert_https_url(url)
    payload: dict[str, Any] = {"name": name, "variables": variables or {}}
    if version is not None:
        payload["version"] = version

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            raw = _post_once(url, payload)
            data = raw.get("data", {})
            result: dict[str, Any] = {
                "content": data.get("content", ""),
                "created_at": data.get("created_at", None),
                "updated_at": data.get("updated_at", None),
                "tags": data.get("tags", []),
            }
            if cache_ttl > 0:
                _prompt_cache[key] = (result, time.time() + cache_ttl)
            return result
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                body = exc.read().decode(errors="replace")
                raise ValueError(f"NirikshaAI get_prompt failed {exc.code}: {body}") from exc
            body = exc.read().decode(errors="replace")
            last_exc = ValueError(f"NirikshaAI get_prompt failed {exc.code}: {body}")
            logger.debug("NirikshaAI get_prompt attempt %d failed %d, retrying", attempt, exc.code)
        except Exception as exc:
            last_exc = exc
            logger.debug("NirikshaAI get_prompt attempt %d error: %s, retrying", attempt, exc)
        if attempt < 3:
            time.sleep(attempt * 0.5)

    logger.warning("NirikshaAI get_prompt %r failed after 3 attempts: %s", name, last_exc)
    raise ValueError(f"NirikshaAI get_prompt error: {last_exc}") from last_exc


def list_prompts() -> list[dict[str, Any]]:
    """List all prompt templates in the project (resolved from API key)."""
    url = f"{_base_url}/api/v1/sdk/prompts"
    _assert_https_url(url)
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            result = _get_once(url)
            return result.get("data", {}).get("prompts", [])
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                body = exc.read().decode(errors="replace")
                raise ValueError(f"NirikshaAI list_prompts failed {exc.code}: {body}") from exc
            body = exc.read().decode(errors="replace")
            last_exc = ValueError(f"NirikshaAI list_prompts failed {exc.code}: {body}")
            logger.debug(
                "NirikshaAI list_prompts attempt %d failed %d, retrying", attempt, exc.code
            )
        except Exception as exc:
            last_exc = exc
            logger.debug("NirikshaAI list_prompts attempt %d error: %s, retrying", attempt, exc)
        if attempt < 3:
            time.sleep(attempt * 0.5)

    logger.warning("NirikshaAI list_prompts failed after 3 attempts: %s", last_exc)
    raise ValueError(f"NirikshaAI list_prompts error: {last_exc}") from last_exc
