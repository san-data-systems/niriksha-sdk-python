"""Internal logging helper for the NirikshaAI SDK.

All SDK log records use the ``nirikshaai`` logger name.
Consumers can configure it via standard :mod:`logging` configuration::

    import logging
    logging.getLogger("nirikshaai").setLevel(logging.DEBUG)
"""

from __future__ import annotations

import logging

_SDK_LOGGER_NAME = "nirikshaai"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the ``nirikshaai`` namespace.

    Args:
        name: Optional sub-name (e.g. ``"eval"``, ``"prompt"``).

    Returns:
        A :class:`logging.Logger` scoped to ``nirikshaai[.name]``.
    """
    if name:
        return logging.getLogger(f"{_SDK_LOGGER_NAME}.{name}")
    return logging.getLogger(_SDK_LOGGER_NAME)
