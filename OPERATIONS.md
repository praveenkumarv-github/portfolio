# Architecture and Operations

## Resource ownership

Terraform manages:

- ACM regional certificate in the baseline state.
- API Gateway custom domain/base-path mapping in the independent domain state.
- Lambda execution role and policy for logs.
- Private AES-256 encrypted S3 Zappa artifact bucket.
- GitHub OIDC provider, branch-scoped deployment role, and deployment policy.

Zappa/CloudFormation manages:

- Lambda function and deployment package configuration.
- API Gateway REST API, stage, deployment, and Lambda integration.
- Lambda invoke permission and supporting Zappa resources.
- Deployment artifacts written to the Terraform-managed S3 bucket.

External/manual resources include the pre-existing Terraform state bucket, domain registration, Cloudflare zone and Access application, Google identity provider, and Google service account. The Phase 2 workflow manages Cloudflare DNS records through a zone-scoped API token; Terraform does not own those records.

## Request and data flow

1. Cloudflare authenticates the approved Google identity.
2. API Gateway invokes the Zappa Lambda application.
3. Django verifies the Cloudflare Access JWT again at the origin.
4. The dashboard loads the last Excel/Google Sheet file from Lambda `/tmp`.
5. The parser resolves AMFI/MFAPI NAV and GoodReturns metal prices.
6. The calculation engine creates the portfolio summary and alerts.
7. SQLite records the current upload path and monthly snapshot.

Portfolio formulas, Excel schema semantics, and alert rules are independent of authentication and deployment configuration.

## Transaction Analytics and XIRR

The MFTransactions sheet (optional) enables per-fund and portfolio-level transaction analytics:

- **XIRR Solver** (`dashboard/services/xirr.py`): pure-Python Newton-Raphson with bisection fallback. No external dependency.
- **Per-fund analytics** (`calculation_engine._fund_transaction_analytics`): invested amount, redeemed amount, net invested, absolute gain, absolute return %, first investment date, transaction list.
- **Portfolio-level analytics** (`calculation_engine._portfolio_mf_analytics`): pools XIRR and gain across only the funds that have a recorded transaction ledger. Funds without a ledger do not inflate pooled gain.
- **Data quality check** (`validators.validate_portfolio_data`): warns if a fund's MFTransactions net units (Invested - Redeemed) do not reconcile within ±0.5% of its declared Units. This catches incomplete or mismatched ledgers.

MFTransactions preferred columns: `Scheme Name`, `Transaction Type`, `Units`, `NAV`, `Amount`, `Date`. The parser resolves Scheme Name to the matching `MutualFunds.FundName` (case and repeated whitespace are ignored), then uses that mutual fund's Identifier for analytics and reconciliation. Transaction Type accepts `PURCHASE`/`REDEEM` (case-insensitive) and is internally normalized to Invested/Redeemed. Amount is optional and auto-computed as `Units × NAV` if not supplied. An unmatched/ambiguous scheme name or invalid transaction type is skipped with a warning. Legacy `FundIdentifier` + `Type` columns remain supported for existing workbooks.

## Economic Asset Allocation (Look-Through)

The economic allocation engine (`dashboard/services/economic_allocation.py`) answers "what do I actually own economically?" by mapping every holding to six standard buckets:

- **Equity, Corporate Debt, Government Securities, Cash, Gold, Other**

Classification priority:
1. Explicit override from the LookThrough sheet (keyed by fund Identifier or instrument Type).
2. Conservative, documented defaults for well-known product types:
   - Equity Fund → 100% Equity
   - Debt Fund → 100% Corporate Debt
   - Gilt Fund → 100% Government Securities
   - Hybrid Fund → 60% Equity / 40% Corporate Debt
   - Arbitrage Fund → 20% Equity / 80% Cash
   - EPF → 85% Govt Securities / 15% Equity (per EPFO published mix)
   - PPF → 100% Govt Securities
   - Cash-like (FD, Savings, RD) → 100% Cash
3. Other/Unclassified: NPS and custom schemes without an override fall here by design (never guessed).

**Equity Style Split** (optional, from LookThrough): Large Cap, Mid Cap, Small Cap, International; otherwise unclassified.

**Hidden Equity Detection**: compares effective equity % (look-through) to naive equity % (Equity/Debt/Hybrid labels). Funds with hidden exposure (e.g., EPF's 15% equity, arbitrage's 20%) can silently increase actual portfolio risk.

**Target Deviations**: optional Targets sheet (AssetClass, TargetPct) computes Current % vs Target % vs Deviation for each bucket. Zero-target buckets are omitted.

LookThrough columns: `Key` (fund Identifier or Type), `Equity`, `CorporateDebt`, `GovtSecurities`, `Cash`, `Gold`, `Other`, optional `EquityLarge`, `EquityMid`, `EquitySmall`, `EquityIntl` (all as %); percentages are normalized to 100.

## Data durability

| Data | Local | Lambda |
|---|---|---|
| SQLite | `db.sqlite3` | `/tmp/db.sqlite3` |
| Uploaded workbook | `media/` | `/tmp/media` |
| NAV cache | `cache/` | `/tmp/cache` |
| Metal cache | `data/` | `/tmp/cache` |

Lambda `/tmp` is ephemeral. A warm environment may retain data, but a cold environment starts with a new database and no workbook. Monthly snapshots are not durable or shared between concurrent Lambda environments. The system is appropriate for one person who can reload source data; use S3/DynamoDB/RDS before treating history as durable.

## Google Sheet behavior

Credential order:

1. Local `GOOGLE_SERVICE_ACCOUNT_JSON`, when explicitly set.
2. No credentials, which selects public export.

When credentials exist, private Drive export is attempted first. If credentials are malformed, dependencies are unavailable, or the service account cannot access that file, the application attempts public export. A private Sheet still fails with a safe access message. Every response must be a structurally valid XLSX ZIP containing workbook metadata before it reaches pandas.

Troubleshooting:

- Confirm Drive API is enabled and the private Sheet is shared with `client_email`.
- For public mode, verify the export URL works without a signed-in browser session.
- Search CloudWatch logs for `[GSheet]`; logs intentionally omit credentials and Sheet IDs.

## Authentication decision

| Option | Assessment |
|---|---|
| Cloudflare Access + Google | Selected: low cost, MFA through Google, edge protection, and origin JWT verification |
| Cognito + Google federation | AWS-native but more setup, callback/session integration, and maintenance for one user |
| Django password login | Simple locally, but durable user/session storage and MFA are awkward on ephemeral Lambda SQLite |
| API Gateway authorizer | Strong but adds Lambda/Cognito integration and operational complexity without improving this use case |

Cloudflare is the perimeter, but Django JWT verification is the enforcement point that prevents an unprotected API Gateway hostname from becoming an authentication bypass.

## Monitoring baseline

Current infrastructure writes Lambda logs but does not provision alarms or explicit log retention. Add these before relying on unattended operation:

- Lambda `Errors`, `Throttles`, `Duration`, and `ConcurrentExecutions` alarms.
- API Gateway 5xx and latency alarms.
- CloudWatch log retention of 14-30 days for a personal dashboard.
- A synthetic check that expects Cloudflare authentication, not HTTP 200.
- AWS Budget alert.

Avoid adding an unauthenticated health endpoint because it weakens the fail-closed origin boundary.

## Local infrastructure validation (Floci)

The `terraform-floci` job in `validate.yml` and `scripts/floci_terraform_check.sh` apply `infra/` against the [Floci](https://github.com/floci-io/floci) local AWS emulator to catch Terraform regressions without touching real AWS. Terraform AWS provider v5 honours `AWS_ENDPOINT_URL`, so no HCL changes are required.

Run locally:

```bash
docker compose -f docker-compose.floci.yml up -d
scripts/floci_terraform_check.sh
docker compose -f docker-compose.floci.yml down
```

Scope and limits:

- Validates baseline resources only (IAM role/policies, S3 artifact bucket, ACM cert record). `enable_github_oidc_role=false` skips the GitHub OIDC provider whose thumbprints are not meaningful against an emulator.
- Does not exercise `infra/domain` because `aws_acm_certificate_validation` needs real DNS.
- Does not exercise Zappa, API Gateway custom domain, or Cloudflare — those require live services.
- Floci uses in-memory storage, so every run is a fresh account. A green run proves the code applies and destroys cleanly; it does not prove real AWS quota, service-linked-role, or IAM condition behavior.

## Incident checks

### Dashboard returns 403

1. Confirm Cloudflare Access application status and exact-email policy.
2. Confirm Lambda variables for enabled flag, team domain, AUD, and email.
3. Confirm Access token issuer is the configured team domain and AUD matches the application.
4. Check whether Cloudflare signing-key retrieval is failing from Lambda.

### Dashboard returns 5xx after deploy

1. Run `zappa tail production` or inspect `/aws/lambda/...` logs.
2. Confirm `DJANGO_SECRET_KEY` was injected.
3. Confirm `pysqlite3-binary`, pandas, and numpy are manylinux x86_64 wheels.
4. Confirm Lambda has 3 GB ephemeral storage and package extraction succeeded.
5. Check cold-start migration errors.

### Google Sheet fails

1. Test a public export without credentials to isolate Google API configuration.
2. Inspect service-account sharing.
3. Confirm Google packages were included in the Zappa artifact.
4. Verify the downloaded response is XLSX rather than a Google login/error page.

## Cost profile

At personal traffic levels, Lambda and API Gateway are usually within free or low usage tiers. Recurring charges primarily come from S3 storage and any Cloudflare plan above its free Zero Trust allowance. Review current provider pricing rather than relying on a fixed estimate.

## Known risks

- No durable application database or workbook storage in Lambda.
- No tenant isolation; design assumes exactly one authorized user.
- Zappa deployment IAM remains broad because it manages CloudFormation, Lambda, API Gateway, S3, IAM, logs, and events. OIDC limits who can assume it, but further least-privilege work should be based on CloudTrail-observed actions.
- Terraform state bucket lifecycle, encryption, versioning, and access controls are bootstrap responsibilities outside this stack. Native S3 lockfiles are enabled for both `prod/terraform.tfstate` and `prod/domain.tfstate` and require Terraform 1.10 or later.
- GoodReturns HTML changes can force stale/manual metal prices; AMFI/MFAPI availability affects mutual-fund freshness.
