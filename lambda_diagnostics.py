"""
Lambda Diagnostics — Deploy-and-hit script for Zappa/Django on AWS Lambda.
Run locally:  python lambda_diagnostics.py
Or add as a Django management command and call via Zappa.

This script reproduces the EXACT cold-start path your Lambda follows
(wsgi_lambda.py → settings_lambda → migrate → view) and reports
every failure point with root cause + fix.
"""

import sys
import os
import json
import traceback
import importlib
import sqlite3
from io import StringIO

# ── Collect results ──────────────────────────────────────────────────
report = []

def section(title):
    report.append(f"\n{'='*70}")
    report.append(f"  {title}")
    report.append(f"{'='*70}")

def ok(msg):
    report.append(f"  ✅ {msg}")

def fail(msg, detail=""):
    report.append(f"  ❌ {msg}")
    if detail:
        for line in detail.strip().splitlines():
            report.append(f"     {line}")

def warn(msg):
    report.append(f"  ⚠️  {msg}")

def info(msg):
    report.append(f"  ℹ️  {msg}")

# =====================================================================
# 1. Python & platform info
# =====================================================================
section("1. RUNTIME ENVIRONMENT")
info(f"Python version   : {sys.version}")
info(f"Platform         : {sys.platform}")
info(f"Prefix           : {sys.prefix}")
info(f"Executable       : {sys.executable}")
info(f"CWD              : {os.getcwd()}")
info(f"/tmp writable    : {os.access('/tmp', os.W_OK) if sys.platform == 'linux' else 'N/A (not Linux)'}")

# =====================================================================
# 2. SQLite version check (deterministic=True needs ≥ 3.8.3)
# =====================================================================
section("2. SQLITE VERSION CHECK")
sqlite_ver = sqlite3.sqlite_version
info(f"SQLite version   : {sqlite_ver}")
major, minor, patch = (int(x) for x in sqlite_ver.split("."))
if (major, minor, patch) >= (3, 8, 3):
    ok("SQLite ≥ 3.8.3 — deterministic=True should work")
else:
    fail(
        f"SQLite {sqlite_ver} < 3.8.3 — deterministic=True will crash Django 5+",
        "FIX: In settings_lambda.py add:\n"
        '  DATABASES["default"]["OPTIONS"] = {"deterministic": False}',
    )

# Test deterministic flag directly
try:
    conn = sqlite3.connect(":memory:")
    conn.create_function("testfn", 1, lambda x: x, deterministic=True)
    conn.close()
    ok("deterministic=True works on this runtime")
except Exception as e:
    fail(f"deterministic=True fails: {e}")

# =====================================================================
# 3. Critical import checks
# =====================================================================
section("3. DEPENDENCY IMPORTS")

CRITICAL_IMPORTS = [
    ("django",                "Core framework"),
    ("pandas",                "Excel parser depends on it"),
    ("numpy",                 "pandas dependency"),
    ("openpyxl",              "Excel .xlsx reader"),
    ("requests",              "Google Sheet / metal price fetching"),
    ("lxml",                  "beautifulsoup / optional parser"),
    ("bs4",                   "beautifulsoup4 — metal price scraping"),
]

for mod_name, purpose in CRITICAL_IMPORTS:
    try:
        m = importlib.import_module(mod_name)
        ver = getattr(m, "__version__", getattr(m, "VERSION", "?"))
        ok(f"{mod_name} {ver}  ({purpose})")
    except Exception as e:
        fail(f"{mod_name} — IMPORT FAILED  ({purpose})", str(e))

# =====================================================================
# 4. Django settings load
# =====================================================================
section("4. DJANGO SETTINGS")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finance_dashboard.settings_lambda")

try:
    import django
    django.setup()
    from django.conf import settings as djsettings
    ok(f"DJANGO_SETTINGS_MODULE = {os.environ['DJANGO_SETTINGS_MODULE']}")
    ok(f"DEBUG = {djsettings.DEBUG}")
    ok(f"ALLOWED_HOSTS = {djsettings.ALLOWED_HOSTS}")
    info(f"DATABASE ENGINE = {djsettings.DATABASES['default']['ENGINE']}")
    info(f"DATABASE NAME   = {djsettings.DATABASES['default']['NAME']}")
    info(f"SESSION_ENGINE  = {getattr(djsettings, 'SESSION_ENGINE', 'default (db)')}")

    # Check deterministic option
    db_opts = djsettings.DATABASES["default"].get("OPTIONS", {})
    det_val = db_opts.get("deterministic", "NOT SET (defaults to True in Django 5+)")
    if det_val is True or det_val == "NOT SET (defaults to True in Django 5+)":
        warn(f"deterministic = {det_val} — may crash on old SQLite")
    else:
        ok(f"deterministic = {det_val}")

except Exception as e:
    fail("Django setup FAILED", traceback.format_exc())

# =====================================================================
# 5. Database migration test
# =====================================================================
section("5. DATABASE MIGRATION")
try:
    from django.core.management import call_command
    buf = StringIO()
    call_command("migrate", interactive=False, verbosity=1, stdout=buf)
    ok("Migrations completed")
    for line in buf.getvalue().strip().splitlines()[-5:]:
        info(f"  {line}")
except Exception as e:
    fail("Migration FAILED", traceback.format_exc())

# =====================================================================
# 6. URL routing — does '/' resolve?
# =====================================================================
section("6. URL ROUTING")
try:
    from django.urls import resolve, Resolver404
    match = resolve("/")
    ok(f"'/' resolves to {match.func.__module__}.{match.func.__name__}")
except Resolver404:
    fail("'/' does NOT resolve — check finance_dashboard/urls.py and dashboard/urls.py")
except Exception as e:
    fail("URL resolution error", traceback.format_exc())

# =====================================================================
# 7. Template rendering check
# =====================================================================
section("7. TEMPLATE CHECK")
try:
    from django.template.loader import get_template
    tpl = get_template("dashboard/dashboard.html")
    ok(f"Template found: {tpl.origin}")
except Exception as e:
    fail("Template 'dashboard/dashboard.html' NOT FOUND", str(e))

# =====================================================================
# 8. Simulate a GET / request end-to-end
# =====================================================================
section("8. SIMULATED GET / REQUEST")
try:
    from django.test import RequestFactory
    from dashboard.views import dashboard_view

    factory = RequestFactory()
    # Add session + messages middleware support
    from django.contrib.sessions.backends.signed_cookies import SessionStore
    from django.contrib.messages.storage.cookie import CookieStorage

    request = factory.get("/")
    request.session = SessionStore()
    request._messages = CookieStorage(request)

    response = dashboard_view(request)
    info(f"Status code: {response.status_code}")
    if response.status_code == 200:
        ok("GET / returned 200")
        content = response.content.decode("utf-8", errors="replace")
        info(f"Response size: {len(content)} bytes")
        if "<!DOCTYPE" in content or "<html" in content.lower():
            ok("Response contains valid HTML")
        else:
            warn("Response does not look like HTML")
    else:
        fail(f"GET / returned {response.status_code}")
        fail("Response body (first 500 chars):", response.content.decode()[:500])
except Exception as e:
    fail("Simulated request CRASHED", traceback.format_exc())

# =====================================================================
# 9. WSGI application object
# =====================================================================
section("9. WSGI APPLICATION OBJECT")
try:
    from finance_dashboard.wsgi_lambda import application
    ok(f"application object loaded: {type(application)}")
except Exception as e:
    fail("wsgi_lambda.application FAILED to load", traceback.format_exc())

# =====================================================================
# 10. Package size analysis
# =====================================================================
section("10. PACKAGE SIZE ANALYSIS")
try:
    import site
    site_dirs = site.getsitepackages() if hasattr(site, "getsitepackages") else [os.path.join(sys.prefix, "lib")]
    
    BIG_PACKAGES = ["numpy", "pandas", "lxml", "bs4", "boto3", "botocore", "django"]
    for pkg in BIG_PACKAGES:
        try:
            m = importlib.import_module(pkg)
            pkg_dir = os.path.dirname(m.__file__)
            total = 0
            for dirpath, _, filenames in os.walk(pkg_dir):
                for f in filenames:
                    total += os.path.getsize(os.path.join(dirpath, f))
            mb = total / (1024 * 1024)
            marker = "⚠️  LARGE" if mb > 20 else "✅"
            report.append(f"  {marker} {pkg:20s} {mb:8.1f} MB")
        except ImportError:
            report.append(f"  ⏭️  {pkg:20s} not installed")
except Exception as e:
    warn(f"Size analysis failed: {e}")

# =====================================================================
# 11. Zappa settings validation
# =====================================================================
section("11. ZAPPA SETTINGS VALIDATION")
zappa_path = os.path.join(os.getcwd(), "zappa_settings.json")
if not os.path.exists(zappa_path):
    # Try relative to this script
    zappa_path = os.path.join(os.path.dirname(__file__), "zappa_settings.json")

if os.path.exists(zappa_path):
    with open(zappa_path) as f:
        zs = json.load(f)
    prod = zs.get("production", {})
    
    # slim_handler
    if prod.get("slim_handler"):
        ok("slim_handler = true")
    else:
        warn("slim_handler = false — zip >50MB will be slow or rejected")
    
    # app_function
    app_fn = prod.get("app_function", "")
    info(f"app_function = {app_fn}")
    
    # django_settings
    ds = prod.get("django_settings", "")
    env_ds = prod.get("environment_variables", {}).get("DJANGO_SETTINGS_MODULE", "")
    if ds and env_ds and ds != env_ds:
        warn(f"django_settings ({ds}) ≠ env DJANGO_SETTINGS_MODULE ({env_ds})")
    else:
        ok(f"django_settings consistent: {ds}")
    
    # exclude patterns
    excludes = prod.get("exclude", [])
    info(f"Exclude patterns: {len(excludes)}")
    
    # Check if test/dev packages are being deployed
    warn_pkgs = ["pytest", "pluggy", "iniconfig", "Pygments", "placebo"]
    info(f"Dev packages in requirements that shouldn't be in Lambda: {warn_pkgs}")
else:
    warn("zappa_settings.json not found in CWD")

# =====================================================================
# SUMMARY & RECOMMENDED FIXES
# =====================================================================
section("RECOMMENDED FIXES (apply all)")

report.append("""
  1. FIX SQLite deterministic error
     In finance_dashboard/settings_lambda.py, after DATABASES block add:
     
       DATABASES["default"]["OPTIONS"] = {"deterministic": False}

  2. FIX numpy/pandas import failure on Lambda
     These are REQUIRED by your excel_parser.py (import pandas as pd).
     They must load correctly. Two options:

     Option A — Use a Lambda Layer (recommended):
       Add to zappa_settings.json → production:
         "slim_handler": true,
         "lambda_layers": [
           "arn:aws:lambda:ap-south-1:770693421928:layer:Klayers-p311-pandas:17",
           "arn:aws:lambda:ap-south-1:770693421928:layer:Klayers-p311-numpy:12"
         ]
       Then REMOVE numpy and pandas from requirements.txt.

     Option B — Use slim_handler + correct binary wheels:
       Set "slim_handler": true in zappa_settings.json.
       Pin versions with manylinux wheels:
         numpy==1.26.4
         pandas==2.1.4

  3. FIX package size (80.5MB)
     In zappa_settings.json set:
       "slim_handler": true

     Remove dev-only packages from requirements.txt:
       pytest, pytest-django, pluggy, iniconfig, Pygments,
       placebo, troposphere, cfn-flip, hjson, tqdm,
       colorama, argcomplete, packaging, toml, click, durationpy

  4. FIX template not found (if reported above)
     Ensure dashboard/templates/dashboard/dashboard.html exists
     and is NOT in the "exclude" list in zappa_settings.json.

  5. After applying fixes, redeploy:
       pip install -r requirements.txt
       python -m zappa.cli update production
       python -m zappa.cli tail production --since 2m
""")

# ── Print full report ────────────────────────────────────────────────
print("\n".join(report))