"""
WSGI config for finance_dashboard project.
"""

# --- ADD THESE 3 LINES AT THE VERY TOP ---
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
# -----------------------------------------

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_dashboard.settings')

application = get_wsgi_application()
