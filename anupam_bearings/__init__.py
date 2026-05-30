"""
Expose Celery app so Django picks it up on startup.
This ensures shared_task() works correctly across all apps.
"""
from .celery import app as celery_app
__all__ = ("celery_app",)
