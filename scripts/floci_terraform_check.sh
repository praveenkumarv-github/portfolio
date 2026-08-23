#!/usr/bin/env bash
# Applies infra/ against the Floci local AWS emulator to prove the Terraform
# code is syntactically and semantically valid without touching real AWS.
#
# Usage:
#   scripts/floci_terraform_check.sh                    # apply + destroy
#   FLOCI_KEEP_STATE=1 scripts/floci_terraform_check.sh # skip destroy
set -euo pipefail

FLOCI_ENDPOINT="${FLOCI_ENDPOINT:-http://localhost:4566}"
INFRA_DIR="${INFRA_DIR:-infra}"

export AWS_ENDPOINT_URL="$FLOCI_ENDPOINT"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"
export AWS_REGION="${AWS_REGION:-ap-south-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export TF_IN_AUTOMATION=1

echo "Waiting for Floci at $FLOCI_ENDPOINT ..."
for _ in $(seq 1 60); do
  if curl -fsS "$FLOCI_ENDPOINT/_localstack/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "$FLOCI_ENDPOINT/_localstack/health" >/dev/null

# Skip resources whose semantics are not meaningfully validatable on Floci
# (GitHub OIDC provider thumbprints, ACM DNS validation via real Route 53).
TF_VARS=(
  -var="domain_name=example.test"
  -var="subdomain=finance"
  -var="project=finance-dash"
  -var="environment=ci"
  -var="aws_region=$AWS_REGION"
  -var="enable_github_oidc_role=false"
)

# Neutralize the real S3 backend so init/apply use ephemeral local state.
OVERRIDE_FILE="$INFRA_DIR/floci_backend_override.tf"
cat > "$OVERRIDE_FILE" <<'HCL'
terraform {
  backend "local" {}
}
HCL
trap 'rm -f "$OVERRIDE_FILE"' EXIT

terraform -chdir="$INFRA_DIR" init -input=false -upgrade
terraform -chdir="$INFRA_DIR" validate
terraform -chdir="$INFRA_DIR" apply -auto-approve -input=false "${TF_VARS[@]}"

echo "--- Terraform outputs from Floci apply ---"
terraform -chdir="$INFRA_DIR" output

# Baseline expectations: role ARN and artifact bucket must be produced.
terraform -chdir="$INFRA_DIR" output -raw lambda_role_arn >/dev/null
terraform -chdir="$INFRA_DIR" output -raw s3_bucket >/dev/null

if [[ -z "${FLOCI_KEEP_STATE:-}" ]]; then
  terraform -chdir="$INFRA_DIR" destroy -auto-approve -input=false "${TF_VARS[@]}"
fi

echo "Floci Terraform smoke check succeeded."