"""
Lambda-specific Django settings.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import * # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in Lambda")

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
if not _raw_hosts:
    raise ImproperlyConfigured("ALLOWED_HOSTS is required in Lambda")
ALLOWED_HOSTS = [host.strip() for host in _raw_hosts.split(",") if host.strip()]

CSRF_TRUSTED_ORIGINS = [
    f"https://*{host}" if host.startswith(".") else f"https://{host}"
    for host in ALLOWED_HOSTS
]

_cloudflare_mode = os.environ.get("CLOUDFLARE_ACCESS_ENABLED", "").strip().lower()
if _cloudflare_mode not in {"true", "false"}:
    raise ImproperlyConfigured("CLOUDFLARE_ACCESS_ENABLED must be explicitly set to true or false")
CLOUDFLARE_ACCESS_ENABLED = _cloudflare_mode == "true"
CLOUDFLARE_ACCESS_TEAM_DOMAIN = os.environ.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "")
CLOUDFLARE_ACCESS_AUDIENCE = os.environ.get("CLOUDFLARE_ACCESS_AUDIENCE", "")
CLOUDFLARE_ACCESS_ALLOWED_EMAIL = os.environ.get("CLOUDFLARE_ACCESS_ALLOWED_EMAIL", "")
if CLOUDFLARE_ACCESS_ENABLED:
    MIDDLEWARE.insert(1, "finance_dashboard.middleware.CloudflareAccessMiddleware")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# Database — /tmp is the only writable path in Lambda
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/db.sqlite3",
    }
}

# Cookie-based sessions & messages prevent DB locking/missing-table errors in Lambda
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# File storage — all under /tmp
MEDIA_ROOT   = "/tmp/media"
MEDIA_URL    = "/media/"
STATIC_ROOT  = "/tmp/static"
STATICFILES_DIRS = []

# Structured CloudWatch Logging
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
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}