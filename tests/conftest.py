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
    # pytest-django connects to the DB (via django.setup()) before this hook
    # runs, which both pins settings.DATABASES into connections._settings
    # (configure_settings() only re-reads settings when _settings is still
    # None) and caches an actual postgres DatabaseWrapper per alias in
    # connections._connections. The settings.DATABASES override above is
    # silently ignored unless we clear both caches here.
    from django.db import connections
    from django.utils.connection import Local
    connections.close_all()
    connections._settings = None
    connections.__dict__.pop('settings', None)
    connections._connections = Local(connections.thread_critical)
    # Disable Celery for tests
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    # CanonicalHostMiddleware 301-redirects any non-canonical Host to
    # SITE_URL whenever DEBUG=False (core/middleware.py) — a prod-only SEO
    # concern that otherwise breaks every view test against the Django
    # test client's default "testserver" host.
    settings.CANONICAL_HOST_REDIRECT = False
    # Same reasoning — SECURE_SSL_REDIRECT (also gated on `not DEBUG`) would
    # 301 every plain-http test-client request to https.
    settings.SECURE_SSL_REDIRECT = False
