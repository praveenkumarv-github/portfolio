"""
ASGI config for finance_dashboard project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finance_dashboard.settings')

application = get_asgi_application()
