"""Entry point to start the Celery worker.

Run:
    python worker.py

Or use the celery CLI directly:
    celery -A celery_app worker --loglevel=info
"""

from celery_app import celery_app  # noqa: F401 — triggers nirikshaai.init()

if __name__ == "__main__":
    celery_app.worker_main(
        argv=["worker", "--loglevel=info", "--concurrency=2"]
    )
