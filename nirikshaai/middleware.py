"""
Middleware helpers for WSGI (Flask, Django) and ASGI (FastAPI, Starlette) apps.

Usage — WSGI::

    from nirikshaai.middleware import NirikshaWSGIMiddleware
    app = NirikshaWSGIMiddleware(app)

Usage — ASGI::

    from nirikshaai.middleware import NirikshaASGIMiddleware
    app = NirikshaASGIMiddleware(app)
"""

from __future__ import annotations


class NirikshaWSGIMiddleware:
    """WSGI middleware that adds OpenTelemetry tracing to any WSGI application."""

    def __init__(self, app):
        try:
            from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

            self._wrapped = OpenTelemetryMiddleware(app)
        except ImportError:
            self._wrapped = app  # graceful no-op if not installed

    def __call__(self, environ, start_response):
        return self._wrapped(environ, start_response)


class NirikshaASGIMiddleware:
    """ASGI middleware that adds OpenTelemetry tracing to any ASGI application."""

    def __init__(self, app):
        try:
            from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

            self._wrapped = OpenTelemetryMiddleware(app)
        except ImportError:
            self._wrapped = app  # graceful no-op

    async def __call__(self, scope, receive, send):
        await self._wrapped(scope, receive, send)
