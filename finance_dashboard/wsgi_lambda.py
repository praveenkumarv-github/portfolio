"""
Lambda WSGI entry point.

Runs Django migrations on cold start (SQLite at /tmp is empty on a
fresh Lambda container) and returns the WSGI application.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finance_dashboard.settings_lambda")

# Auto-migrate on cold start — safe to run repeatedly (no-op when up to date)
try:
    import django
    django.setup()
    from django.core.management import call_command
    call_command("migrate", "--run-syncdb", verbosity=0)
except Exception:
    pass  # never crash Lambda startup; UI will surface DB errors naturally

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
