# Dashboard Audit Status

**Reviewed:** 2026-10-31, against the working tree. This replaces the speculative
2026-09-04 HTML recommendations. It is an implementation/verification record,
not a completed penetration test, accessibility certification, or deployment sign-off.

## Implemented Corrections

| Area | Current behavior | Main evidence |
|------|------------------|---------------|
| Google exports | Validated HTTPS Google IDs; bounded public reads and size-checked private chunks | [google_sheet_service.py](dashboard/services/google_sheet_service.py), [url_utils.py](dashboard/services/url_utils.py), service tests |
| XIRR | Invalid/non-finite/same-day inputs and arithmetic failures return no rate rather than a misleading guess/crash | [xirr.py](dashboard/services/xirr.py), [test_xirr.py](tests/test_xirr.py) |
| FIFO average cost | Remaining purchase-lot cost divided by remaining units, not net cash after sale proceeds | [capital_gains.py](dashboard/services/capital_gains.py), [test_capital_gains.py](tests/test_capital_gains.py) |
| Numeric inputs | Reject non-finite portfolio numbers; skip invalid transaction rows with warnings | [excel_parser.py](dashboard/services/excel_parser.py), [validators.py](dashboard/services/validators.py), parser/hardening tests |
| Monthly snapshots | Parser errors prevent partial results overwriting an existing monthly snapshot | [aggregator.py](dashboard/services/aggregator.py), [test_aggregator.py](tests/test_aggregator.py) |
| CSV export | Quote cells, escape quotes, neutralize formula-leading text | [dashboard.html](dashboard/templates/dashboard/dashboard.html), [test_dashboard_ui.py](tests/test_dashboard_ui.py) |
| CI PassRole | Restricted to the application execution role with Lambda service condition | [github_actions.tf](infra/github_actions.tf); local Terraform validation |
| Dependency pins | Django 5.2.17, PyJWT 2.15.0, certifi 2026.10.18, urllib3 2.8.0, Werkzeug 3.1.9 | [requirements.txt](requirements.txt), [requirements-deploy.txt](requirements-deploy.txt); pinned dependency audit |

The follow-up release-artifact audit found nine advisory entries for the previous
cryptography 46.0.6 pin. [requirements-lambda-native.txt](requirements-lambda-native.txt)
now pins **cryptography 50.0.0**. Its CPython 3.11/manylinux2014 wheels are available;
the repeated audit of 65 resolved release artifacts found no known vulnerabilities.

Gold and silver fallback values are zero when no usable live/cache price exists.
Insurance is still excluded from net worth. Holding-period analytics remain an
approximation, not a tax-liability calculation.

## History and UI Status

- Explicit **Update Net Worth** POST saves one date-only record from the loaded
  portfolio. Reload the original Google Sheet first when its contents change.
- Eligible local Excel sessions use CSV. Configured cloud sessions use daily
  JSON objects in the existing private Zappa bucket, not a new bucket or S3 Tables.
- Same-day writes replace the value, including decreases. S3 versioning retains
  old writes; different dates use independent objects.
- The Lambda role can list/read/write only the history prefix. Cleanup preserves
  buckets containing history versions and stops if inspection fails.
- Demo history contains 54 samples across one year in a separate local CSV.
  Cloud demo actions are denied; storage failures do not silently fall back.
- The trend chart is full-width with calendar 3M/6M/1Y/All filters and responsive
  sizing. History reads are outside the cached portfolio payload.
- Theme switching and exports already exist. PDF uses browser printing; the
  export labeled Excel produces CSV, not a native XLSX workbook.
- Several tables already have column scopes and status badges contain text.
  The old report's blanket absence claims are no longer accurate.

See [FEATURES_DETAILED.md](FEATURES_DETAILED.md) for calculation/storage contracts
and [OPERATIONS.md](OPERATIONS.md) for backup and incident procedures.

## Remaining Risks

1. **Deployment permissions remain broad.** Restricting PassRole does not remove
   the broad IAM creation/attachment and S3 actions available to CI. Further
   reduction needs a reviewed deployment model and staging verification.
2. **Shared single-user state.** Loaded workbooks and history are not isolated
   by user or source. Do not expose this deployment as a multi-tenant service.
3. **Ephemeral active data.** Lambda workbooks, caches, and monthly SQLite history
   still live in `/tmp`. Reload a workbook after cold start to display durable
   S3 history; no historical SQLite migration or scheduled daily save is provided.
4. **Backup and retention.** S3 versioning also retains deployment artifacts and
   costs storage. Administrators can still delete all versions. Maintain an
   independent history backup and exclude it from destructive lifecycle rules.
5. **External frontend dependencies.** Chart.js 4.4.0 loads from a CDN without
   SRI. CDN availability/integrity and Google Fonts remain external dependencies.
6. **Accessibility/performance not certified.** Keyboard/focus handling,
   disclosure states, remaining table semantics, contrast and screen-reader
   behavior need a dedicated review. No measured paint-time, CSS-size saving,
   or comprehensive performance result is claimed.
7. **Runtime drift.** Local Python 3.14 validation does not establish Python 3.11
   Lambda behavior. Local pandas/NumPy pins differ from the native Lambda set.
8. **Origin protection is configuration-dependent.** Enable Cloudflare Access
   origin JWT verification and verify direct API denial after deployment.
   A valid stolen Access application token can reach the origin until expiry.
9. **Monitoring gaps.** This stack does not provision CloudWatch alarms/retention,
   budgets, or WAF. Terraform backend security is managed outside this stack.

## Verification Record

On 2026-10-31, `python -m pytest -q` completed with **230 passed, 1 skipped** on
Windows/Python 3.14.10, Django 5.2.17, and cryptography 50.0.0. The Node-dependent CSV test skipped
because Node is unavailable. The real browser CSV helper was exercised earlier
in the session with formula prefixes, whitespace and quote cases.

- Added 15 real-signature JWT cases: valid identity, expiry, future issue time,
  issuer/audience/email mismatch, each missing required claim, wrong signing key,
  wrong algorithm, malformed token, and unavailable JWKS. Only key retrieval is
  mocked; RSA signing, JWT parsing, signature and claim validation execute.
- Added private-download boundary cases: exactly at the byte limit succeeds;
  the first chunk exceeding the limit aborts before requesting another chunk.
  Optional Google SDK boundaries are stubbed; no Google request is made.
- Both Terraform stacks validate, recursive format checks pass, and initialization
  used `-backend=false -lockfile=readonly`. No infrastructure was applied.
- Django system checks and migration drift checks pass. Production checks with
  synthetic configuration report W005/W021 only: HSTS subdomains and preload
  remain disabled intentionally. Do not enable either without domain-wide review.
- The native-wheel gate downloads 10 compatible wheels for CPython 3.11 and
  manylinux2014. The wider release check resolved 65 artifacts for Python 3.11.14,
  building the source-only `placebo==0.9.0` as a pure-Python wheel first.
- Advisory scans passed for development requirement pins and the 65 release
  artifacts, including resolved transitives. Host-dependent dependency markers
  and actual Lambda imports still require Linux CI; this is not deployed proof.
- Earlier browser chart/date-filter, stubbed S3, cleanup, and bucket-wiring checks
  remain applicable. No coverage percentage is asserted.

## Bandit Triage

Command: `python -m bandit -r dashboard finance_dashboard scripts manage.py generate_sample_excel.py lambda_diagnostics.py -f json`.

The scan completed without parse errors or suppressed findings: **0 high,
11 medium, 2 low**. It returns nonzero because the following findings remain
visible, not because the scanner failed. No blanket exclusions were added.

| Rule | Count | Review and disposition |
|------|-------|------------------------|
| B108: fixed temporary paths | 9 medium | Two diagnostic checks, four NAV/metal cache references, three Lambda storage settings. Lambda `/tmp` is execution-environment scoped; local Linux caches still use predictable `/tmp/cache`. Use a trusted single-user host; shared-host isolation remains a risk. |
| B310: URL opening | 2 medium | Google export and Cloudflare DNS code construct fixed HTTPS hosts; sheet IDs are validated. Redirect behavior still trusts those upstream services. |
| B105: hardcoded secret | 1 low | Development-only key; Lambda settings replace it with a required environment secret. Never deploy with local settings. |
| B110: ignored exception | 1 low | Workbook close failure in `finally`; parsing failures are not swallowed by this block. |

## External Release Gates

Not performed: live AWS deployment/IAM/S3 checks, production Cloudflare tests,
Ubuntu/Python 3.11 execution, or the Floci integration job. Python 3.11, Node and
Docker were not found in the local environment. A cross-platform wheel download
does not replace those execution gates. Comprehensive accessibility/performance
audits remain outside this local security pass.

The consolidated dated record is in
[DOCUMENTATION_UPDATES_SUMMARY.md](DOCUMENTATION_UPDATES_SUMMARY.md).
