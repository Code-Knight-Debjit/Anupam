"""
anupam_bearings/celery.py
──────────────────────────
Celery application instance for Anupam Bearings.

Celery handles:
  - Async LLM calls (so HTTP response returns immediately)
  - Background RAG indexing jobs
  - Redis-based result caching

Worker startup:
  celery -A anupam_bearings worker --loglevel=info --concurrency=4

Beat scheduler (for periodic tasks):
  celery -A anupam_bearings beat --loglevel=info
"""

import os
from celery import Celery

# Tell Celery which Django settings module to use
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "anupam_bearings.settings")

app = Celery("anupam_bearings")

# Load config from Django settings, using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS (looks for tasks.py in each)
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Sanity check task — call with: debug_task.delay()"""
    print(f"Request: {self.request!r}")
