Ran terminal command:  cd /c/data/tools/personal/port && cat zappa_settings.json

Read [](file:///c%3A/data/tools/personal/port/infra/variables.tf)

Read [](file:///c%3A/data/tools/personal/port/infra/outputs.tf)

Read [](file:///c%3A/data/tools/personal/port/infra/iam.tf#1-1), lines 1 to 80

Read [](file:///c%3A/data/tools/personal/port/finance_dashboard/settings_lambda.py#1-1), lines 1 to 40

Read [](file:///c%3A/data/tools/personal/port)

Read [](file:///c%3A/data/tools/personal/port/requirements.txt)

Read [](file:///c%3A/data/tools/personal/port/finance_dashboard/wsgi_lambda.py)

Here are both deliverables:

---

## 1 — AWS Setup: Single Snippet

```bash
# ============================================================
# Personal Finance Dashboard — AWS Deploy Runbook
# Run every command top-to-bottom, once, in order.
# Prerequisites: AWS CLI configured, Terraform ≥ 1.5, Python 3.11
# ============================================================


# ── 0. ONE-TIME LOCAL SETUP ─────────────────────────────────

git clone <your-repo-url> && cd port

python3.11 -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install zappa google-auth google-auth-httplib2 google-api-python-client


# ── 1. TERRAFORM PHASE 1 — core infra ───────────────────────
# Creates: S3 deploy bucket · IAM Lambda role · IAM Zappa deploy policy
#          Secrets Manager shell · ACM certificate · Route53 hosted zone

cd infra

terraform init                        # connect to Terraform Cloud backend

terraform apply \
  -var="domain_name=yourdomain.com" \
  -var="subdomain=finance" \
  -var="project=finance-dash" \
  -var="aws_region=ap-south-1"

# !! IMPORTANT: copy the 4 nameservers from output "route53_nameservers"
# and set them as NS records at your domain registrar NOW.
# ACM cert validation and Route53 routing both require this.

terraform output                      # save all outputs; you need 3 below:
# s3_bucket          → REPLACE_WITH_TF_OUTPUT_s3_bucket
# lambda_role_arn    → REPLACE_WITH_TF_OUTPUT_lambda_role_arn
# zappa_deploy_policy_arn → attach to your AWS deploy user (next step)

cd ..


# ── 2. GRANT YOUR DEPLOY USER ZAPPA PERMISSIONS ─────────────

# Replace DEPLOY_USER with your actual AWS IAM user name
aws iam attach-user-policy \
  --user-name DEPLOY_USER \
  --policy-arn $(cd infra && terraform output -raw zappa_deploy_policy_arn)


# ── 3. FILL zappa_settings.json ─────────────────────────────

S3=$(cd infra && terraform output -raw s3_bucket)
ROLE=$(cd infra && terraform output -raw lambda_role_arn)
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Edit these three lines directly in zappa_settings.json:
#   "s3_bucket": "$S3"
#   "role_arn":  "$ROLE"
#   "DJANGO_SECRET_KEY": "$SECRET_KEY"
#   "ALLOWED_HOSTS": "finance.yourdomain.com"

# On Linux/macOS you can use sed:
sed -i "s|REPLACE_WITH_TF_OUTPUT_s3_bucket|$S3|g"          zappa_settings.json
sed -i "s|REPLACE_WITH_TF_OUTPUT_lambda_role_arn|$ROLE|g"  zappa_settings.json
sed -i "s|REPLACE_WITH_STRONG_SECRET|$SECRET_KEY|g"        zappa_settings.json
sed -i "s|finance.yourdomain.com|finance.yourdomain.com|g" zappa_settings.json  # already correct


# ── 4. LOAD GOOGLE SERVICE ACCOUNT (if using private sheets) ─

# Flatten key.json to single line and inject into Lambda env:
SA_JSON=$(python -c "import json,sys; print(json.dumps(json.load(open('key.json'))))")

# Option A — via Secrets Manager (recommended; reference at runtime):
aws secretsmanager put-secret-value \
  --secret-id $(cd infra && terraform output -raw secret_arn) \
  --secret-string "$SA_JSON"

# Option B — directly in zappa_settings.json env vars (simpler, less secure):
# Set "GOOGLE_SERVICE_ACCOUNT_JSON": "$SA_JSON"  inside environment_variables


# ── 5. COLLECT STATIC FILES ─────────────────────────────────

python manage.py collectstatic --noinput \
  --settings=finance_dashboard.settings_lambda


# ── 6. ZAPPA DEPLOY (first time) ────────────────────────────

zappa deploy production
# Output will print:
#   Deploying...
#   Your application is now live at: https://xxxxxxxxxx.execute-api.ap-south-1.amazonaws.com/production

# Save the API Gateway ID from the URL (the xxxxxxxxxx part):
APIGW_ID=xxxxxxxxxx


# ── 7. TERRAFORM PHASE 2 — custom domain wiring ─────────────

cd infra
terraform apply \
  -var="domain_name=yourdomain.com" \
  -var="subdomain=finance" \
  -var="project=finance-dash" \
  -var="aws_region=ap-south-1" \
  -var="zappa_api_gateway_id=$APIGW_ID" \
  -var="zappa_stage_name=production"
cd ..

# Uncomment domain + certificate_arn in zappa_settings.json, then:
# CERT_ARN=$(cd infra && terraform output -raw acm_certificate_arn)
# zappa certify production    ← wires ACM cert to API GW custom domain


# ── 8. SMOKE TEST ────────────────────────────────────────────

curl -s -o /dev/null -w "%{http_code}" https://finance.yourdomain.com/
# Expect: 200

# View Lambda logs live:
zappa tail production


# ── 9. FUTURE UPDATES ───────────────────────────────────────

zappa update production          # re-deploy code changes
zappa rollback production -n 1   # revert one version
zappa undeploy production        # tear down Lambda (keeps Terraform infra)
```

---

## 2 — Full System Bible (prompt-ready)

---

```
======================================================================
PERSONAL FINANCE DASHBOARD — COMPLETE SYSTEM BIBLE
Version: May 2026  |  Runtime: Python 3.11 Lambda / 3.14 local
======================================================================

TABLE OF CONTENTS
─────────────────
1.  Purpose & Design Philosophy
2.  Tech Stack
3.  Repository Layout
4.  Data Model (Excel schema)
5.  Service Layer Architecture
6.  Django App Layer
7.  Frontend (dashboard.html)
8.  Lambda Runtime Architecture
9.  Terraform Infrastructure
10. Settings Files
11. Zappa Configuration
12. Test Suite
13. Google Sheets Integration
14. NAV Fetching (Mutual Funds)
15. Metal Price Fetching
16. Security Model
17. Cost Model
18. Operational Runbook
19. Known Constraints & Trade-offs
20. Extension Points

======================================================================
1. PURPOSE & DESIGN PHILOSOPHY
======================================================================

A personal-use, local-first financial cockpit.
- Primary input: Excel workbook (.xlsx) with named sheets
- Secondary input: Google Sheets URL (private via Service Account, or public)
- Output: Single-page dashboard with net worth, asset allocation,
  mutual fund breakdown, metals, emergency fund coverage, insurance, alerts
- Hosting target: AWS Lambda + API Gateway → ~$1.50–2/mo
- No auth layer (personal use, HTTPS at domain level)
- No build pipeline (Chart.js via CDN, CSS inline)
- No external DB (SQLite at /tmp on Lambda, project root locally)

Design rules:
- Services NEVER raise to views — every public method returns a safe value
- Each pipeline stage is independently try/excepted
- Lambda /tmp is treated as ephemeral; in-memory fallback always present
- Tests must run with zero network access (all external calls mocked)

======================================================================
2. TECH STACK
======================================================================

Layer           | Technology
─────────────────────────────────────────────────────
Web framework   | Django 5.0.4
Data parsing    | pandas ≥ 2.0, openpyxl ≥ 3.1
Charts          | Chart.js 4.4.0 (CDN, no npm)
HTTP calls      | requests ≥ 2.31 (lazy imported in services)
HTML parsing    | beautifulsoup4 ≥ 4.12 + lxml (lazy imported)
Database        | SQLite (local: db.sqlite3; Lambda: /tmp/db.sqlite3)
Serverless      | Zappa ≥ 0.59 + AWS Lambda (Python 3.11 runtime)
API Gateway     | AWS REST API Gateway (created by Zappa)
CDN / Domain    | Route53 + ACM + API Gateway Custom Domain
IaC             | Terraform ≥ 1.5 (Terraform Cloud backend)
Secrets         | AWS Secrets Manager (Google SA JSON)
Tests           | pytest + pytest-django (89 tests, all passing)
Google Sheets   | google-auth + google-api-python-client (optional, lazy)

======================================================================
3. REPOSITORY LAYOUT
======================================================================

port/
├── manage.py
├── requirements.txt              # core deps; zappa/google commented out
├── pytest.ini
├── zappa_settings.json           # Lambda deploy config
│
├── finance_dashboard/            # Django project package
│   ├── settings.py               # base settings (local dev)
│   ├── settings_lambda.py        # Lambda overrides (imports settings.py)
│   ├── wsgi.py                   # standard WSGI (local)
│   ├── wsgi_lambda.py            # Lambda entry point + cold-start migrate
│   └── urls.py
│
├── dashboard/                    # Django app
│   ├── models.py                 # FileUploadHistory, NetWorthSnapshot
│   ├── views.py                  # thin controllers; no business logic
│   ├── urls.py
│   ├── templates/dashboard/
│   │   └── dashboard.html        # single-page SPA-like template
│   └── services/
│       ├── aggregator.py         # orchestration; mtime cache
│       ├── calculation_engine.py # financial logic; PortfolioSummary
│       ├── excel_parser.py       # sheet-to-dict parsing
│       ├── validators.py         # sanity checks; never raises
│       ├── nav_service.py        # AMFI + MFAPI NAV with /tmp cache
│       ├── metal_price_service.py# GoodReturns scrape with /tmp cache
│       ├── google_sheet_service.py # Drive API + public export URL
│       └── url_utils.py          # Google Sheet ID extraction
│
├── infra/                        # Terraform
│   ├── main.tf                   # provider + backend
│   ├── variables.tf
│   ├── outputs.tf
│   ├── s3.tf                     # deploy bucket
│   ├── iam.tf                    # Lambda exec role + Zappa deploy policy
│   ├── secrets.tf                # Secrets Manager for SA JSON
│   ├── acm.tf                    # ACM certificate (ap-south-1)
│   ├── route53.tf                # hosted zone + cert validation + A alias
│   └── apigateway_domain.tf      # custom domain + base path mapping
│
├── tests/
│   ├── test_aggregator.py
│   ├── test_calculation_engine.py
│   ├── test_dashboard_ui.py
│   ├── test_excel_parser.py
│   ├── test_google_sheet_integration.py
│   ├── test_google_sheet_service.py
│   ├── test_hardening.py
│   ├── test_lambda_runtime.py    # Lambda/edge-case tests (new)
│   ├── test_metal_price_service.py
│   └── test_nav_service.py
│
├── data/                         # local metal price cache (gitignored)
├── cache/                        # local NAV cache (gitignored)
└── media/                        # uploaded Excel files (gitignored)

======================================================================
4. DATA MODEL (Excel schema)
======================================================================

Sheet name      | Required columns
──────────────────────────────────────────────────────────────────
MutualFunds     | FundName, Units, Identifier (AMFI scheme code)
Retirement      | Type (EPF/PPF/NPS/etc.), Amount
Liquid          | AccountName, Type (Savings/Current/etc.), Amount
EmergencyFund   | AccountName, Type (FD/Savings/etc.), Amount, MaturityDate
Insurance       | Type (Term/Health/etc.), Provider, Premium, Coverage
Metals          | Type (Gold/Silver), Quantity (grams)

Rules:
- Sheet names are case-insensitive during parsing
- Extra columns are ignored
- Missing sheets → empty list (never crashes)
- All monetary values assumed INR

======================================================================
5. SERVICE LAYER ARCHITECTURE
======================================================================

Request flow:
  views.py → aggregator.build_dashboard_context(file_path)
               │
               ├─► excel_parser.parse_excel_file(path) → raw dict
               ├─► validators.validate_portfolio_data(data) → warnings[]
               ├─► calculation_engine.build_portfolio(data) → PortfolioSummary
               │     ├─► nav_service.get_nav(scheme_code) [per MF row]
               │     └─► metal_price_service.get_metal_price(metal) [Gold/Silver]
               ├─► alerts.run_alerts(portfolio) → alert strings
               └─► aggregator._capture_snapshot(portfolio) → DB write

aggregator.py:
  - Caches payload in _PAYLOAD_CACHE dict keyed by (file_path, mtime)
  - Cache is invalidated on new file upload (clear_dashboard_cache())
  - Each pipeline stage wrapped in independent try/except (no-crash guarantee)

calculation_engine.py:
  - build_portfolio(raw_data) → PortfolioSummary dataclass
  - Net worth = MF + Retirement + Liquid + EF + Metals  (Insurance EXCLUDED)
  - _classify_fund_type(): Equity/Debt/Hybrid via type column or name keywords
  - _ef_alert(): EF coverage months → "error" (<3m) / "warn" (3–6m) / "ok" (≥6m)
  - PortfolioSummary.categories: list of (name, value, pct) for pie chart

validators.py:
  - validate_portfolio_data(data) → list[str] warning messages
  - Checks: NAV bounds (0 < nav < 10000), metal price bounds, negative totals
  - Never raises; attaches warnings to payload dict

======================================================================
6. DJANGO APP LAYER
======================================================================

models.py:
  FileUploadHistory
    - file_path: CharField  (path to .xlsx or /tmp/media/gsheets/latest_gsheet.xlsx)
    - uploaded_at: DateTimeField(auto_now_add=True)
    - source: CharField ("Local File" | "Google Sheet")

  NetWorthSnapshot
    - snapshot_date: DateField
    - net_worth: DecimalField
    - created_at: DateTimeField

views.py  (all views redirect on error; never 500):
  dashboard(request)          GET  → renders dashboard.html
  upload_file(request)        POST → saves Excel, sets active file in session
  load_google_sheet(request)  POST → fetches sheet, copies to stable path,
                                     saves FileUploadHistory
  refresh_nav(request)        POST → clears aggregator cache, redirects
  set_metal_price(request)    POST → manual metal override

Key internal helpers:
  _is_google_temp_file(path) → True for "gsheet_*" OR "latest_gsheet.xlsx"
  _delete_previous_loaded_file() → removes old file before saving new one

Active file resolution order (views.py → aggregator):
  1. session["uploaded_file"]  (most recently uploaded)
  2. FileUploadHistory.objects.first() (latest DB record)
  3. None → dashboard shows "upload a file" prompt

======================================================================
7. FRONTEND (dashboard.html)
======================================================================

Single Jinja2/Django template. No npm, no webpack.
Chart.js 4.4.0 loaded from cdnjs CDN.
All CSS is inline (no external stylesheet).

Blades (collapsible sections):
  - Net Worth Summary     (always visible)
  - Mutual Funds          (auto-open on DOMContentLoaded)
  - Asset Allocation      (pie chart)
  - Retirement
  - Liquid Assets
  - Emergency Fund        (color-coded by coverage months)
  - Insurance
  - Metals
  - Risk Management       (auto-open on DOMContentLoaded)
  - Alerts panel          (red/yellow banners)

Top bar inputs:
  - Google Sheet URL field + "Load Sheet" button
  - Excel file upload input + "Upload" button
  - Source/timestamp display (shows which file is active)

Chart IDs:
  #allocationChart  → doughnut (asset allocation %)
  #mfSplitChart     → doughnut (Equity/Debt/Hybrid split)

======================================================================
8. LAMBDA RUNTIME ARCHITECTURE
======================================================================

Entry point: finance_dashboard/wsgi_lambda.py
  - Sets DJANGO_SETTINGS_MODULE = finance_dashboard.settings_lambda
  - Runs migrate --run-syncdb on cold start (try/except, never crashes)
  - Returns get_wsgi_application()

Lambda constraints handled:
  Constraint              | Solution
  ───────────────────────────────────────────────────────────
  Only /tmp is writable   | _resolve_cache_path() → /tmp/cache/...
                          | MEDIA_ROOT = /tmp/media
                          | DATABASES.NAME = /tmp/db.sqlite3
  /tmp ephemeral          | _MEM_CACHE: Dict = {} in nav + metal services
                          | shutil.copy2 to stable /tmp/media path
  Cold start latency      | slim_handler: true, keep_warm: false
  Timeout 30s             | All HTTP calls have timeout=3s
  Package size            | use_precompiled_packages: true
                          | venv/, tests/, *.md, infra/ excluded from zip

Cache path resolution (both nav_service and metal_price_service):
  def _resolve_cache_path():
      if os.path.isdir("/tmp"):             # Lambda
          d = "/tmp/cache"
      else:                                 # local dev
          d = "<project_root>/data"  OR  "<project_root>/cache"
      os.makedirs(d, exist_ok=True)
      return os.path.join(d, "<filename>.json")

  _MEM_CACHE: Dict = {}   # module-level; survives within same container

Google Sheet stable path:
  Temp file from fetch → shutil.copy2 → /tmp/media/gsheets/latest_gsheet.xlsx
  Temp file deleted via open_google_sheet() context manager (finally block)

======================================================================
9. TERRAFORM INFRASTRUCTURE
======================================================================

All infra is in infra/. Two-phase apply.

Phase 1 (no Zappa yet):
  s3.tf           | S3 bucket for Zappa deploy zip
                  | Public access blocked, AES256, 30-day lifecycle
  iam.tf          | Lambda exec role (Logs + Secrets Manager only)
                  | Zappa deploy policy (scoped to project functions + bucket)
  secrets.tf      | Secrets Manager secret (shell only; value loaded manually)
                  | ignore_changes = [secret_string]
  acm.tf          | ACM certificate (us-east-1 for CloudFront? No — ap-south-1
                  | for regional API GW)  ← DNS validated
  route53.tf      | Public hosted zone, cert validation CNAME records,
                  | A-alias to API GW custom domain

Phase 2 (after zappa deploy):
  apigateway_domain.tf | Custom domain resource
                       | Base path mapping (conditional on zappa_api_gateway_id != "")

Variables needed:
  domain_name           e.g. "yourdomain.com"
  subdomain             e.g. "finance"
  project               e.g. "finance-dash"
  environment           e.g. "prod"
  aws_region            "ap-south-1"  (Mumbai)
  zappa_api_gateway_id  "" (Phase 1) → actual ID (Phase 2)
  zappa_stage_name      "production"

Outputs:
  lambda_role_arn        → paste into zappa_settings.json role_arn
  s3_bucket              → paste into zappa_settings.json s3_bucket
  secret_arn             → use with aws secretsmanager put-secret-value
  zappa_deploy_policy_arn → attach to IAM deploy user
  dashboard_url          → https://finance.yourdomain.com
  route53_nameservers    → set at domain registrar (CRITICAL)

======================================================================
10. SETTINGS FILES
======================================================================

finance_dashboard/settings.py (base — local dev):
  DEBUG = True
  DATABASES: SQLite at db.sqlite3 (project root)
  MEDIA_ROOT: media/ (project root)
  STATICFILES_DIRS: dashboard/static/

finance_dashboard/settings_lambda.py (Lambda override):
  Imports: from .settings import *
  DEBUG = False
  SECRET_KEY: from env DJANGO_SECRET_KEY
  ALLOWED_HOSTS: from env ALLOWED_HOSTS (comma-separated)
  CSRF_TRUSTED_ORIGINS: ["https://{h}" for h in ALLOWED_HOSTS if h != "*"]
  DATABASES.NAME: /tmp/db.sqlite3
  MEDIA_ROOT: /tmp/media
  STATIC_ROOT: /tmp/static
  STATICFILES_DIRS: []      ← must be empty (no local static dir in zip)
  MEDIA_URL: /media/
  Logging: CloudWatch-compatible JSON handler

======================================================================
11. ZAPPA CONFIGURATION (zappa_settings.json)
======================================================================

Key: "production"

  app_function          finance_dashboard.wsgi_lambda.application
  aws_region            ap-south-1
  s3_bucket             <from terraform output s3_bucket>
  role_arn              <from terraform output lambda_role_arn>
  runtime               python3.11
  timeout_seconds       30
  memory_size           512
  django_settings       finance_dashboard.settings_lambda
  slim_handler          true     (smaller zip)
  keep_warm             false    (cost saving; personal use)
  use_precompiled_packages true  (avoids C extension build issues)

  environment_variables:
    DJANGO_SETTINGS_MODULE      finance_dashboard.settings_lambda
    DJANGO_SECRET_KEY           <64-char hex secret>
    ALLOWED_HOSTS               finance.yourdomain.com
    GOOGLE_SERVICE_ACCOUNT_JSON <single-line JSON from key.json>

  exclude (from Lambda zip):
    .git, .gitignore, .env, **/__pycache__, **/*.pyc,
    tests/, venv/, .pytest_cache/, *.md, infra/,
    cache/, data/, media/, db.sqlite3, *.xlsx, key.json

  Phase-2 additions (uncomment after terraform phase 2):
    domain          finance.yourdomain.com
    certificate_arn <ACM cert ARN from terraform output>

======================================================================
12. TEST SUITE
======================================================================

89 tests total. All run with: pytest -q
No network calls — all external I/O mocked.
RequestFactory used (not Django test client) for Python 3.14 compat.

File                              | Count | What it covers
───────────────────────────────────────────────────────────────────
test_aggregator.py                |  2    | mtime cache, clear cache
test_calculation_engine.py        |  2    | MF split, allocation
test_dashboard_ui.py              |  1    | chart canvas IDs
test_excel_parser.py              | 13    | all sheet parsers
test_google_sheet_integration.py  |  6    | load success, invalid URL,
                                  |       | private sheet, network fail,
                                  |       | Excel upload, parsing parity
test_google_sheet_service.py      |  6    | URL extraction, download,
                                  |       | non-xlsx payload rejection
test_hardening.py                 |  8    | empty dataset, extreme values,
                                  |       | validator warnings, resilience
test_lambda_runtime.py            | 11    | _resolve_cache_path, _MEM_CACHE
                                  |       | fallback, context manager cleanup,
                                  |       | allocation sum, insurance exclusion
test_metal_price_service.py       | 19    | live fetch, HTML resilience,
                                  |       | cache fallback, manual override,
                                  |       | corruption handling
test_nav_service.py               | 21    | AMFI fallback, MFAPI fallback,
                                  |       | cache read/write, stale cache,
                                  |       | timeout behavior

======================================================================
13. GOOGLE SHEETS INTEGRATION
======================================================================

google_sheet_service.py exports:
  fetch_google_sheet(sheet_url) → str (temp file path)
  open_google_sheet(sheet_url)  → context manager (auto-deletes temp)

Auto-detection logic:
  if env GOOGLE_SERVICE_ACCOUNT_JSON is set:
      → private mode: Drive API v3 download as xlsx
  else:
      → public mode: https://docs.google.com/spreadsheets/d/{ID}/export?format=xlsx

Private mode (_fetch_private):
  - Lazy imports: google.oauth2.service_account, googleapiclient.discovery
  - Parses SA JSON from env var
  - Drive API files().export(fileId, mimeType=xlsx)
  - Raises GoogleSheetAccessError on 403/404

Public mode (_fetch_public):
  - urllib.request with 20s timeout
  - Validates response starts with b"PK" (ZIP magic bytes = valid xlsx)
  - Raises GoogleSheetError on non-xlsx payload

open_google_sheet(url) — context manager:
  try:
      path = fetch_google_sheet(url)
      yield path
  finally:
      contextlib.suppress(OSError): os.unlink(path)

url_utils.extract_google_sheet_id(url):
  - Accepts /spreadsheets/d/{ID}/ format
  - Accepts ?id={ID} format
  - Validates host is docs.google.com
  - Raises InvalidGoogleSheetUrl on failure

======================================================================
14. NAV FETCHING (Mutual Funds)
======================================================================

nav_service.py — 4-layer fallback:
  1. In-memory cache (_MEM_CACHE dict)  — fastest, same container
  2. File cache (/tmp/cache/nav_cache.json or project root)
  3. AMFI live fetch (https://www.amfiindia.com/spages/NAVAll.txt, 3s timeout)
  4. MFAPI.in fallback (https://api.mfapi.in/mf/{code}, 3s timeout)
  5. Stale cache (any age) as last resort

Cache structure (nav_cache.json):
  { "119551": { "nav": 87.45, "timestamp": "2026-05-01", "name": "..." }, ... }

_resolve_cache_path():
  Lambda → /tmp/cache/nav_cache.json
  Local  → <project_root>/cache/nav_cache.json

_MEM_CACHE: Dict = {}  (module-level, survives container reuse)

_read_cache(): reads file first; falls back to dict(_MEM_CACHE) on any exception
_write_cache(data): sets _MEM_CACHE = dict(data) FIRST; then atomic file write

======================================================================
15. METAL PRICE FETCHING
======================================================================

metal_price_service.py — 3-layer fallback:
  1. Fresh file/memory cache (today's date)
  2. Live scrape from GoodReturns Chennai page (3s timeout)
  3. Stale cache (any age)
  4. Hard-coded safe defaults (Gold: ₹9,200/g, Silver: ₹110/g)

Scraping strategies (resilient to HTML changes):
  A. Known table class "gold-rate-table" → 1-gram row
  B. Any table with adjacent "1 gram" cell
  C. Regex on page text as final fallback

Validation bounds:
  Gold:   ₹1,000 – ₹200,000 per gram
  Silver: ₹10 – ₹5,000 per gram

Manual override: set_manual_price(metal, price) → persists to cache with manual=True
  Manual prices are NOT overwritten by refresh_prices()

Cache: same _resolve_cache_path() + _MEM_CACHE pattern as NAV service

======================================================================
16. SECURITY MODEL
======================================================================

- No user authentication (personal use only; access controlled at domain/VPN level)
- HTTPS enforced: ACM cert + API Gateway custom domain
- CSRF_TRUSTED_ORIGINS set from ALLOWED_HOSTS in settings_lambda.py
- DJANGO_SECRET_KEY: 64-char hex, stored only in Lambda env var
- Google SA JSON: stored in Secrets Manager; injected as env var at deploy time
- key.json excluded from Lambda zip (in zappa exclude list + .gitignore)
- S3 deploy bucket: public access blocked, AES256 encrypted
- IAM Lambda exec role: Logs + Secrets Manager only (no S3, no EC2, no IAM)
- Zappa deploy policy: scoped to project function names + deploy bucket only
- No SQL injection surface (SQLite ORM only; no raw queries)
- DEBUG = False in Lambda settings

======================================================================
17. COST MODEL
======================================================================

Service          | Usage assumption              | Est. monthly cost
─────────────────────────────────────────────────────────────────────
Lambda           | 1000 req/mo, 512MB, 2s avg    | ~$0.00 (free tier)
API Gateway      | 1000 req/mo                   | ~$0.004
Route53          | 1 hosted zone                 | $0.50
ACM              | 1 cert                        | $0.00 (free)
S3               | < 1 MB deploy zip             | ~$0.02
Secrets Manager  | 1 secret, 0 rotations         | $0.40
CloudWatch Logs  | minimal logs                  | ~$0.10
─────────────────────────────────────────────────────────────────────
TOTAL                                            | ~$1.06 – $1.50/mo

======================================================================
18. OPERATIONAL RUNBOOK
======================================================================

DEPLOY / UPDATE
  zappa deploy production      ← first time
  zappa update production      ← subsequent code changes
  zappa certify production     ← after Phase 2 terraform (custom domain)

VIEW LOGS
  zappa tail production
  zappa tail production --since 1h

ROLLBACK
  zappa rollback production -n 1

TEARDOWN (Lambda only; keeps Terraform infra)
  zappa undeploy production

FULL TEARDOWN
  zappa undeploy production
  cd infra && terraform destroy

ROTATE SECRET KEY
  NEW_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
  # Update DJANGO_SECRET_KEY in zappa_settings.json
  zappa update production

REFRESH GOOGLE SA CREDENTIALS
  aws secretsmanager put-secret-value \
    --secret-id <secret_arn> \
    --secret-string "$(python -c "import json; print(json.dumps(json.load(open('key.json'))))")"
  # Also update GOOGLE_SERVICE_ACCOUNT_JSON in zappa_settings.json
  zappa update production

RUN TESTS LOCALLY
  source venv/Scripts/activate   # or source venv/bin/activate on Mac/Linux
  pytest -q

======================================================================
19. KNOWN CONSTRAINTS & TRADE-OFFS
======================================================================

1. SQLite on Lambda /tmp
   - Each cold start = empty DB (FileUploadHistory lost)
   - Mitigated: active file stored in session + stable gsheet path persists
     within same container; snapshots are cosmetic not critical

2. No persistent file storage
   - Uploaded Excel files are lost on cold start
   - Mitigated: Google Sheet URL can be re-fetched; user re-uploads on new container
   - NOT mitigated for production critical workflows (use RDS if needed)

3. Zappa + Python 3.14
   - Lambda runtime must be 3.11; local dev uses 3.14
   - settings_lambda.py and wsgi_lambda.py tested on 3.11 syntax only

4. GoodReturns scraping
   - HTML structure can change silently; 3 fallback strategies + safe defaults
   - Scraping ToS: personal use only

5. Single-region deployment (ap-south-1)
   - No DR / multi-region; acceptable for personal finance tool

6. No caching between Lambda invocations (except _MEM_CACHE on warm containers)
   - Cold start = AMFI + GoodReturns fetch (up to 6s for first request)
   - keep_warm = false by design (cost saving)

======================================================================
20. EXTENSION POINTS
======================================================================

Add new asset class:
  1. Add sheet to Excel template
  2. Add parser in excel_parser.py
  3. Add field to raw_data dict
  4. Add calculation in calculation_engine.py
  5. Add validator bounds in validators.py
  6. Add blade in dashboard.html
  7. Add tests in test_excel_parser.py + test_calculation_engine.py

Add authentication:
  - Use Django allauth or simple token middleware
  - Set DEBUG=False already done; just add LOGIN_REQUIRED middleware

Add persistent storage:
  - Replace SQLite with RDS Postgres; update DATABASES in settings_lambda.py
  - Add VPC config to zappa_settings.json
  - Expected cost delta: +$15–25/mo (RDS t4g.micro)

Add multi-user support:
  - FileUploadHistory needs user FK
  - Session-based active file already works per-user

Add NAV history chart:
  - NetWorthSnapshot model already captures daily net worth
  - Add Chart.js time-series chart using snapshot data

Add CI/CD:
  - GitHub Actions: pytest on PR, zappa update on merge to main
  - Attach zappa_deploy_policy_arn to GitHub OIDC role

======================================================================
END OF BIBLE
======================================================================
```