"""conftest.py — overrides Redis+DB for test environment (no external services needed)."""
import django

def pytest_configure(config):
    from django.conf import settings
    # In-memory cache — no Redis required
    settings.CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
    }
    # Simple SQLite for tests
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
            'TEST': {'NAME': ':memory:'},
        }
    }
    # Disable Celery for tests
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
