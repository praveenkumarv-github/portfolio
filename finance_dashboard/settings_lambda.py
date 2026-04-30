"""
Lambda-specific Django settings.

Extends base settings with overrides required for AWS Lambda:
  - SQLite at /tmp (writable by Lambda)
  - No local static dirs (template CSS/JS is inline)
  - ALLOWED_HOSTS from env var
  - Secret key from env var
  - CSRF trusted origins for custom domain
  - Structured CloudWatch logging
"""

import os

from .settings import *  # noqa: F401,F403

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)  # noqa: F405

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()] or ["*"]

# Required in Django 4+ for CSRF protection when behind API Gateway
_custom_domain = os.environ.get("ALLOWED_HOSTS", "").split(",")[0].strip()
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h != "*"]

# --------------------------------------------------------------------------
# Database — /tmp is the only writable path in Lambda
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/db.sqlite3",
    }
}

# --------------------------------------------------------------------------
# File storage — all under /tmp so no EFS dependency
# --------------------------------------------------------------------------
MEDIA_ROOT   = "/tmp/media"
MEDIA_URL    = "/media/"
STATIC_ROOT  = "/tmp/static"
STATICFILES_DIRS = []      # no local static source dirs in Lambda

# --------------------------------------------------------------------------
# Logging — stdout → CloudWatch Logs
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "dashboard": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
