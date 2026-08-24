"""Guards against the instrumentation manifest drifting from the loader.

_LLM_INSTRUMENTATIONS in nirikshaai/_otel.py lists what init() tries to
instrument; the "llm" extra in pyproject.toml lists what pip installs. If an
entry appears only in the loader it is never installed, and _try_instrument
swallows the resulting ImportError — so the integration silently does nothing.

That is exactly what happened: llama_index, mistralai and google_generativeai
were in the loader but not in the extra, so `pip install nirikshaai[llm]`
delivered three of six advertised instrumentors with no error anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

from nirikshaai._otel import (
    _BUILTIN_LLM_INSTRUMENTORS,
    _GENERAL_INSTRUMENTATIONS,
    _LLM_INSTRUMENTATIONS,
)

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _extra(name: str) -> list[str]:
    """Read one optional-dependencies list out of pyproject.toml.

    Parsed with a regex rather than tomllib because the SDK supports Python 3.9
    and tomllib only landed in 3.11. Adding tomli purely for a test is not worth
    a dependency, and the block is a plain literal list of strings.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\s*=\s*\[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert match, f"could not find the {name!r} extra in {PYPROJECT}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _distributions(requirements: list[str]) -> set[str]:
    """Reduce requirement strings to bare distribution names."""
    return {re.split(r"[<>=!~\[;]", req, maxsplit=1)[0].strip() for req in requirements}


def _module_to_distribution(module_path: str) -> str:
    """Map opentelemetry.instrumentation.foo_bar -> opentelemetry-instrumentation-foo-bar."""
    return module_path.replace(".", "-").replace("_", "-")


def test_every_llm_instrumentor_is_pinned() -> None:
    """A loader entry with no pinned distribution is dead code."""
    pinned = _distributions(_extra("llm"))
    missing = {
        lib: _module_to_distribution(module)
        for lib, module in _LLM_INSTRUMENTATIONS.items()
        if _module_to_distribution(module) not in pinned
    }
    assert not missing, (
        "these instrumentors are attempted by _otel.py but not pinned in the "
        f"'llm' extra, so they are never installed: {missing}"
    )


def test_every_pinned_llm_distribution_is_loaded() -> None:
    """A pinned distribution nothing loads is dead weight in the install."""
    loaded = {_module_to_distribution(m) for m in _LLM_INSTRUMENTATIONS.values()}
    unused = _distributions(_extra("llm")) - loaded
    assert not unused, (
        "these distributions are pinned in the 'llm' extra but never "
        f"instrumented by _otel.py: {unused}"
    )


def test_instrumentation_module_paths_are_well_formed() -> None:
    for lib, module in _LLM_INSTRUMENTATIONS.items():
        assert module.startswith("opentelemetry.instrumentation."), (
            f"{lib} maps to an unexpected module path: {module}"
        )


def test_no_duplicate_module_paths() -> None:
    """Two keys pointing at one module means one of them never applies."""
    seen: dict[str, str] = {}
    for lib, module in _LLM_INSTRUMENTATIONS.items():
        assert module not in seen, f"{lib} and {seen[module]} both map to {module}"
        seen[module] = lib


def test_llm_and_general_sets_are_disjoint() -> None:
    """Instrumenting the same library twice raises at runtime."""
    overlap = set(_GENERAL_INSTRUMENTATIONS.values()) & set(_LLM_INSTRUMENTATIONS.values())
    assert not overlap, f"module instrumented in both general and LLM sets: {overlap}"


def test_llm_extra_is_not_empty() -> None:
    """A parser regression would make every other check here vacuously pass."""
    assert _extra("llm"), "the 'llm' extra must pin at least one instrumentor"


# ── built-in instrumentors ────────────────────────────────────────────────────
#
# These need the opposite guarantees from the third-party ones: no pin (there is
# no distribution to pin), but they must actually import, since a typo here is
# not caught by pip.


def test_builtin_instrumentors_live_in_this_package() -> None:
    """A built-in entry pointing at a third-party module belongs in the other dict."""
    for lib, module in _BUILTIN_LLM_INSTRUMENTORS.items():
        assert module.startswith("nirikshaai.instrumentors."), (
            f"{lib} maps to {module}, which is not a built-in instrumentor"
        )


def test_builtin_instrumentors_import_and_expose_an_instrumentor() -> None:
    """The loader finds the class by name, so a rename would silently no-op.

    _try_instrument scans for an attribute ending in "Instrumentor" and does
    nothing if there is none — no error, no log. For a third-party package that
    is the right behaviour (the library just is not installed); for our own code
    it is a bug that would ship unnoticed.
    """
    import importlib

    for lib, module_path in _BUILTIN_LLM_INSTRUMENTORS.items():
        mod = importlib.import_module(module_path)
        found = [attr for attr in dir(mod) if attr.endswith("Instrumentor")]
        assert found, f"{lib} ({module_path}) exposes no *Instrumentor class"


def test_builtin_instrumentors_do_not_duplicate_third_party_ones() -> None:
    """Hand-maintaining an instrumentor that also exists upstream is pure cost."""
    overlap = set(_BUILTIN_LLM_INSTRUMENTORS) & set(_LLM_INSTRUMENTATIONS)
    assert not overlap, (
        f"these frameworks are instrumented twice, built-in and third-party: {overlap}"
    )


def test_builtin_instrumentors_are_not_pinned_as_distributions() -> None:
    """A built-in must not also appear in the extra — there is nothing to install."""
    pinned = _distributions(_extra("llm"))
    for lib, module in _BUILTIN_LLM_INSTRUMENTORS.items():
        assert _module_to_distribution(module) not in pinned, (
            f"{lib} is built in but also pinned in the 'llm' extra"
        )
