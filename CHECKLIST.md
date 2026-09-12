# Zero → running app: crisp checklist

## 0. External accounts

- [ ] Register a domain (e.g. `karynxt.xyz`).
- [ ] AWS account + IAM user with admin (for bootstrap only).
- [ ] GitHub repo `praveenkumarv-github/portfolio` on branch `fea-v2`.
- [ ] Cloudflare account.
- [ ] Google account + (optional) Google Cloud project.

## 1. Cloudflare zone + Access

- [ ] Add domain to Cloudflare → copy nameservers → set them at registrar → wait for status **Active**.
- [ ] Zero Trust → **Settings → Authentication** → add **Google** (OAuth Client ID + Secret from Google Cloud).
- [ ] Zero Trust → **Access → Applications** → self-hosted app for `finance.<your-domain>` → Allow policy with your exact Gmail only → copy **AUD tag**.
- [ ] My Profile → **API Tokens** → create token with `Zone:DNS:Edit` scoped to this zone only → save token.
- [ ] Note the **Zone ID** (Overview page).

## 2. (Optional) Local Google Sheet service account

- [ ] Google Cloud → enable **Drive API** → create service account → download `key.json` → share the Sheet with its `client_email` as Viewer.

## 3. AWS Terraform state bucket (one-time)

```bash
aws configure                                        # personal admin creds
export AWS_REGION=ap-south-1
export BUCKET=finance-dash-tfstate-875636131680

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration '{
    "Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]
  }'

aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 4. Bootstrap GitHub OIDC role locally (one-time)

```bash
git clone https://github.com/praveenkumarv-github/portfolio && cd portfolio
terraform -chdir=infra init
terraform -chdir=infra apply \
  -target=aws_iam_openid_connect_provider.github \
  -target=aws_iam_role.github_actions_deploy \
  -target=aws_iam_policy.github_actions_deploy \
  -target=aws_iam_role_policy_attachment.github_actions_deploy \
  -var="domain_name=<your-domain>" \
  -var="github_owner=praveenkumarv-github" \
  -var="github_repo=portfolio" \
  -var="github_branch=fea-v2"

terraform -chdir=infra output github_actions_role_arn   # copy this
```

## 5. GitHub repo configuration

**Settings → Secrets and variables → Actions → Secrets**

- [ ] `AWS_GITHUB_ACTIONS_ROLE_ARN` — from step 4
- [ ] `DJANGO_SECRET_KEY` — `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- [ ] `CLOUDFLARE_ACCESS_AUDIENCE` — AUD tag from step 1
- [ ] `CLOUDFLARE_ACCESS_ALLOWED_EMAIL` — your Gmail
- [ ] `CLOUDFLARE_API_TOKEN` — token from step 1

**Variables**

- [ ] `DOMAIN_NAME=<your-domain>`
- [ ] `SUBDOMAIN=finance`
- [ ] `PROJECT_NAME=finance-dash`
- [ ] `ENVIRONMENT=prod`
- [ ] `ALLOWED_HOSTS=finance.<your-domain>,.amazonaws.com`
- [ ] `CLOUDFLARE_ACCESS_ENABLED=true`
- [ ] `CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com`
- [ ] `CLOUDFLARE_ZONE_ID=<zone id>`
- [ ] `DEPLOY_BRANCH=fea-v2`

- [ ] Push `fea-v2` → wait for **Validate** workflow ✓.

## 6. Phase 1 — Baseline + Lambda

- [ ] Actions → **Phase 1 - Deploy Infrastructure and Lambda** → Run workflow → `zappa_stage=production` → wait ✓.

## 7. Phase 2 — DNS + custom domain

- [ ] Actions → **Phase 2 - Deploy Cloudflare and Domain** → Run workflow → `zappa_stage=production` → wait ✓.

## 8. Verify

- [ ] `https://finance.<your-domain>/` → Cloudflare login → Google sign-in → dashboard loads.
- [ ] `curl -i https://<api-id>.execute-api.ap-south-1.amazonaws.com/production/` → **HTTP 403**.
- [ ] Upload sample XLSX or paste a public Google Sheet URL → portfolio renders.

## 9. Everyday ops

- App change: push → **Phase 1**.
- Cert / DNS / mapping change: **Phase 2**.
- Rollback: `zappa rollback production -n 1`.
- Teardown: **Destroy Lambda App** workflow (type `DESTROY`).

## 10. Workbook Preparation (Optional Advanced Features)

The dashboard works with a minimal Excel workbook containing the six required sheets. For XIRR, gain analysis, and economic asset allocation, add optional sheets:

### MFTransactions (Optional: Per-Fund XIRR and Gain Analysis)
Track SIP or lump-sum investments per mutual fund to enable XIRR, absolute return %, and transaction history:

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| Scheme Name | Text | UTI Nifty 50 Index Fund Direct Growth | Must match FundName in MutualFunds (case/repeated whitespace ignored) |
| Transaction Type | Text | PURCHASE | Or REDEEM (case-insensitive); unknown types are skipped with a warning |
| Units | Number | 173.393 | Units bought/sold |
| NAV | Number | 173.0145 | NAV on transaction date |
| Amount | Number | 10,000 | Transaction value; optional because Units × NAV is used when omitted |
| Date | Date | 2025-08-07 | Transaction date (earliest first within a fund) |

- The parser resolves Scheme Name to the corresponding MutualFunds Identifier.
- Amount is auto-computed as `Units × NAV` when it is omitted.
- All dates must be in the past (≤ today) for XIRR to solve.
- At least 2 cashflows (e.g., 1 investment + current value) are required for a meaningful XIRR.
- The validator warns if a fund's total (Invested - Redeemed) units don't match its declared Units; fix the ledger to avoid gain/XIRR inaccuracy.
- Legacy `FundIdentifier` + `Type` sheets remain accepted, but new rows should use this Scheme Name format.

### LookThrough (Optional: Economic Asset Allocation Overrides)
Declare the underlying economic mix of funds and retirement instruments to see "what you actually own" vs. product labels:

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| Key | Text | 120716 or NPS | Fund Identifier or instrument Type (PF, EPF, NPS, FD, Cash, etc.) |
| Equity | Number | 50 | Percent in equity bucket |
| CorporateDebt | Number | 30 | Percent in corporate debt bucket |
| GovtSecurities | Number | 20 | Percent in government securities |
| Cash | Number | 0 | Percent in cash |
| Gold | Number | 0 | Percent in gold |
| Other | Number | 0 | Percent in other/unclassified |
| (Optional) EquityLarge | Number | 60 | Equity style: large cap % |
| (Optional) EquityMid | Number | 25 | Mid cap % |
| (Optional) EquitySmall | Number | 15 | Small cap % |
| (Optional) EquityIntl | Number | 0 | International % |

- Percentages are normalized to 100 by the parser.
- Without overrides, defaults are used: Equity Funds → 100% Equity; Debt Funds → 100% Corporate Debt; Hybrid → 60/40; EPF → 85% Govt Sec / 15% Equity; NPS → Unclassified (no guess).
- Use this sheet to surface hidden equity (e.g., EPF's 15%, arbitrage fund's 20% equity slice).

### Targets (Optional: Deviation Analysis)
Specify your target allocation to see Current % vs. Target % vs. Deviation for each asset class:

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| AssetClass | Text | Equity | Bucket label (Equity, Corporate Debt, Government Securities, Cash, Gold) |
| TargetPct | Number | 55 | Target percentage for this class |

- Deviation = (Current % - Target %) in percentage points.
- Positive deviation = over target; negative = under target.
- Omit a row to have no target for that class.

### Sample Workbook Generation
Run locally to generate a complete sample with realistic SIP data:

```bash
python generate_sample_excel.py
```

Output: `sample_finance_data.xlsx` with 6 required sheets + 12-month SIP example + NPS override + Targets.

