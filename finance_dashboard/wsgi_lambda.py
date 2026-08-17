"""
Lambda WSGI entry point.

Runs Django migrations on cold start (SQLite at /tmp is empty on a
fresh Lambda container) and returns the WSGI application.
"""

__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import os
import django
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finance_dashboard.settings_lambda")

django.setup()

try:
    # Migrate default Django tables (sessions, contenttypes, etc.) and custom models
    call_command("migrate", interactive=False, verbosity=0)
except Exception as e:
    print(f"[WSGI Startup Migration Error]: {e}")

application = get_wsgi_application()