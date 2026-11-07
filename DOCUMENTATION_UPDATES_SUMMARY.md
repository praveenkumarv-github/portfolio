# Documentation Updates Summary

**Reviewed:** 2026-10-31 against the local working tree. This supersedes the
2026-09-07 summary. All ten repository Markdown documents were refreshed in
place; no new documentation files were needed. Generated/dependency Markdown is
outside this review. Implementation status is not deployment status.

## Document Index

| Document | Updated scope |
|----------|---------------|
| [README.md](README.md) | Current features, security pins, daily CSV/S3 history, deployment and limits |
| [AI_CONTEXT.md](AI_CONTEXT.md) | Compact source-based briefing, current storage and security invariants |
| [AI_FULL_REPO_PROMPT.md](AI_FULL_REPO_PROMPT.md) | Working rules distinguish ephemeral state from existing durable history |
| [CHECKLIST.md](CHECKLIST.md) | Setup/save/recovery verification, workbook rules and release checks |
| [CODEBASE_ARCHITECTURE.md](CODEBASE_ARCHITECTURE.md) | Real modules, models, data shapes, orchestration/cache boundaries and tests |
| [FEATURES_DETAILED.md](FEATURES_DETAILED.md) | Actual APIs, corrected financial examples, XIRR/FIFO/allocation/history behavior |
| [OPERATIONS.md](OPERATIONS.md) | Daily save semantics, backup/cleanup, shared history, incidents and risks |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Existing-bucket wiring, prefix-scoped Lambda IAM, restricted PassRole and release procedures |
| [DASHBOARD_AUDIT.md](DASHBOARD_AUDIT.md) | Implemented fixes, remaining risks, evidence and unverified gates |
| [DOCUMENTATION_UPDATES_SUMMARY.md](DOCUMENTATION_UPDATES_SUMMARY.md) | This dated index and verification ledger |

## Main Corrections

- Daily history is explicit, date-based and separate from legacy monthly SQLite
  snapshots. Local CSV and its demo file remain isolated; cloud history uses the
  existing private versioned Zappa bucket and never accepts demo writes.
- Update Net Worth saves the loaded valuation, not a new Google fetch. Same-day
  saves replace values, including decreases. Cloud dates use Django's time zone
  (currently UTC); CSV dates use the local computer date.
- History is shared per deployment. Lambda workbook/SQLite state is still
  ephemeral. S3 versioning/cleanup protection is not an independent backup.
- Corrected remaining FIFO average cost, XIRR bounds/invalid-input behavior,
  actual parser data shapes, target normalization, and transaction validation.
- Removed invented test names/APIs, mismatched currency/unit examples, unsupported
  coverage percentages, and claims that models were unused or future dates rejected.
- Documented bounded Google downloads, safe CSV exports, finite-number checks,
  protection against partial monthly snapshots, restricted CI PassRole and
  dependency security updates.
- Replaced the speculative HTML audit's already-implemented feature requests and
  unmeasured performance estimates with current behavior and remaining risks.

## Verification Ledger

### Latest regression run

Command: `python -m pytest -q`, using the selected Windows Python 3.14.10
interpreter with Django 5.2.17 and cryptography 50.0.0.

Result on **2026-10-31**: **231 collected, 230 passed, 1 skipped**.
The CSV JavaScript test skips because Node is unavailable locally. No coverage
measurement was run; no percentage is claimed. Counts are dated evidence, not
permanent expectations for future checkouts.

### Documentation checks

All ten repository Markdown files were checked: local link targets exist,
fenced code blocks are balanced, and review dates are present. Editor diagnostics
reported no errors. A targeted consistency scan found no superseded security
pins, obsolete test/coverage claims, or the corrected parser/date-rule assertions.
This checks local targets and source consistency, not external URLs or rendered
Mermaid diagrams.

### Audit completion checks

| Check | Result and boundary |
|-------|---------------------|
| Targeted financial/input/storage regressions | Passed; the latest full suite includes the landed tests |
| Root/domain Terraform validate and format checks | Both passed using the actual executable; backend-disabled initialization and unchanged lockfiles; no apply |
| Django checks | System checks and migration drift pass; production check reports only HSTS W005/W021 under synthetic configuration |
| Real-signature JWT regressions | 15 new cases exercise RSA signing, signature verification, required claims and fail-closed behavior; only JWKS retrieval mocked |
| Private-download limit regressions | Exact-limit success and first-over-limit abort; Google SDK stubbed without external requests |
| Bandit | No scan errors; 0 high, 11 medium, 2 low, all triaged in DASHBOARD_AUDIT; findings retained without blanket suppressions |
| Native wheel availability | 10 wheels downloaded for CPython 3.11/manylinux2014_x86_64, including cryptography 50.0.0 |
| Workflow/settings bucket wiring | Existing Terraform bucket reused for Zappa and history; no new secret |
| S3 and cleanup behavior | Tested with botocore/CLI stubs, not live S3 writes or deletions |
| Local browser chart | Desktop 1440px and mobile 390px inspected; 54 demo samples; 3M/6M/1Y date filters checked |
| Browser CSV helper | Formula prefixes, leading whitespace, quotes and ordinary numeric text exercised |
| Development dependency audit | Explicit local requirement pins report no known vulnerabilities; not an audit of every globally installed package |
| Resolved release dependency audit | 65 candidate artifacts, including transitives, report no known vulnerabilities after the cryptography upgrade; Python 3.11.14/manylinux2014 target with a locally built pure-Python placebo wheel |

Security pins are Django 5.2.17, PyJWT 2.15.0, certifi 2026.10.18, urllib3 2.8.0,
and Werkzeug 3.1.9 in both main requirements files; cryptography 50.0.0 is pinned
in the native requirements included by deployment. The follow-up resolved scan
found nine advisory entries in cryptography 46.0.6, prompting that upgrade.
The scan then passed using `--no-deps --disable-pip` against a generated manifest
of all downloaded artifact versions, rather than only direct requirement pins.
Host-dependent markers and actual installed/deployed packages still require
target-platform validation; advisory results are point-in-time evidence.

### Not verified

- No live AWS/Terraform apply, Lambda deployment, production IAM/S3 or Cloudflare
  validation was performed for these changes.
- Python 3.11, Node and Docker were not found locally. Ubuntu/Python 3.11 execution,
  the Node-only CSV regression, and Floci integration remain CI release gates.
  Native wheel availability was verified, but not actual Lambda native imports.
- Comprehensive accessibility and performance audits were not performed.
- JWT tests exercise real cryptography but use synthetic keys and mocked JWKS
  retrieval; production Cloudflare key fetching/rotation still needs a live check.
- No measured coverage or exhaustive tax-correctness claim is made. FIFO holding
  periods use an approximate 365-day rule, not complete asset-specific tax law.

## Follow-up Release Gates

Use the checklists in [DEPLOYMENT.md](DEPLOYMENT.md) and
[CHECKLIST.md](CHECKLIST.md). Run target-runtime validation, re-audit the final
installed release dependencies, verify origin denial and daily cloud persistence after authorized
deployment, and keep an independent backup of the history prefix. Review broad
deployment IAM and shared-state limitations before expanding beyond one user.
