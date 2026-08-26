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
