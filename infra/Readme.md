```
═══════════════════════════════════════════════════════════════
  FINANCE DASHBOARD — AWS LAMBDA SETUP (Step by Step)
═══════════════════════════════════════════════════════════════

PRE-REQUISITES
──────────────
• AWS CLI configured (aws configure)
• Terraform >= 1.5 installed
• Python 3.11 + pip installed locally
• Domain purchased (e.g. example.com)
• Google Cloud project with Sheets API + Drive API enabled
  → Create a Service Account → download key JSON

═══════════════════════════════════════════════════════════════
STEP 1 — GOOGLE SERVICE ACCOUNT
═══════════════════════════════════════════════════════════════

1. Go to console.cloud.google.com → APIs & Services → Credentials
2. Create Service Account → download JSON key
3. Open your Google Sheet → Share → paste service-account email
   (e.g. finance-dash@project.iam.gserviceaccount.com)
   Role: Viewer
4. Flatten the key JSON to a single line:
   python -c "import json,sys; print(json.dumps(json.load(open('key.json'))))"
   → save output — you'll need it in Step 4

═══════════════════════════════════════════════════════════════
STEP 2 — TERRAFORM PHASE 1 (infra scaffolding)
═══════════════════════════════════════════════════════════════

cd infra/

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
aws_region  = "ap-south-1"
domain_name = "example.com"        # your purchased domain
subdomain   = "finance"
project     = "finance-dash"
environment = "prod"
EOF

terraform init
terraform apply
# ↓ copy these 3 outputs:
#   lambda_role_arn       → used in zappa_settings.json
#   s3_bucket             → used in zappa_settings.json
#   route53_nameservers   → set at your registrar (next step)

═══════════════════════════════════════════════════════════════
STEP 3 — POINT YOUR DOMAIN TO ROUTE 53
═══════════════════════════════════════════════════════════════

At your domain registrar:
  Change NS records → paste the 4 nameservers from terraform output
  (DNS propagation: 5 min – 48 hrs)

═══════════════════════════════════════════════════════════════
STEP 4 — LOAD SECRET INTO SECRETS MANAGER
═══════════════════════════════════════════════════════════════

aws secretsmanager put-secret-value \
  --region ap-south-1 \
  --secret-id finance-dash/google-service-account \
  --secret-string file://key.json

═══════════════════════════════════════════════════════════════
STEP 5 — CONFIGURE zappa_settings.json
═══════════════════════════════════════════════════════════════

Edit zappa_settings.json → fill in:

  "s3_bucket":  "<s3_bucket from Step 2 output>"
  "role_arn":   "<lambda_role_arn from Step 2 output>"
  "DJANGO_SECRET_KEY":            "<generate: python -c 'import secrets; print(secrets.token_hex(32))'>"
  "ALLOWED_HOSTS":                "finance.example.com"
  "GOOGLE_SERVICE_ACCOUNT_JSON":  "<single-line JSON from Step 1.4>"

═══════════════════════════════════════════════════════════════
STEP 6 — INSTALL LAMBDA DEPENDENCIES
═══════════════════════════════════════════════════════════════

# In the project root (activate your venv first)
source venv/Scripts/activate       # Windows
# or: source venv/bin/activate     # Linux/macOS

pip install zappa google-auth google-auth-httplib2 google-api-python-client

═══════════════════════════════════════════════════════════════
STEP 7 — DEPLOY WITH ZAPPA
═══════════════════════════════════════════════════════════════

zappa deploy production

# Output will include a line like:
#   Your Zappa deployment is live!
#   https://abc123xyz.execute-api.ap-south-1.amazonaws.com/production
#
# Note the API ID from the URL: abc123xyz  ← you need this

═══════════════════════════════════════════════════════════════
STEP 8 — TERRAFORM PHASE 2 (wire custom domain)
═══════════════════════════════════════════════════════════════

cd infra/

# Add to terraform.tfvars:
echo 'zappa_api_gateway_id = "abc123xyz"' >> terraform.tfvars

terraform apply
# → creates base-path mapping → finance.example.com goes live

═══════════════════════════════════════════════════════════════
STEP 9 — VERIFY
═══════════════════════════════════════════════════════════════

curl -I https://finance.example.com
# expect: HTTP/2 200

# Test Google Sheet load:
# Open https://finance.example.com
# Paste your private Sheet URL → click "Load from Google Sheet"
# Dashboard should render with your data

═══════════════════════════════════════════════════════════════
STEP 10 — FUTURE UPDATES
═══════════════════════════════════════════════════════════════

# Any code change:
zappa update production

# View live logs:
zappa tail production

# Rollback:
zappa rollback production -n 1

═══════════════════════════════════════════════════════════════
COST REMINDER  ~$1.50–2.00 / month
  Route 53 hosted zone  $0.50
  API Gateway HTTP      $0.50
  Secrets Manager       $0.40
  S3 artifacts          $0.05
  Lambda invocations    ~$0.10  (personal usage)
═══════════════════════════════════════════════════════════════
```