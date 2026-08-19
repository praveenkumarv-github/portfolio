#!/usr/bin/env bash

# ==============================================================================
# AWS Resource Cleanup Script (Extremely Verbose Mode)
# ==============================================================================
# This script inventories and permanently deletes AWS resources created by the
# Terraform and Zappa deployment pipelines for the 'finance-dash' project.
#
# It includes detailed logging, robust S3 deletion, error capturing, and 
# interactive confirmations.
# ==============================================================================

set -euo pipefail

# ==============================================================================
# Default Configuration & Environment Variables
# ==============================================================================
echo "[INFO] Loading environment variables and setting defaults..."

AWS_REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-finance-dash}"
ENVIRONMENT="${ENVIRONMENT:-prod}"
ZAPPA_PROJECT="${ZAPPA_PROJECT:-portfolio}"
ZAPPA_STAGE="${ZAPPA_STAGE:-production}"
DOMAIN_NAME="${DOMAIN_NAME:-karynxt.xyz}"
SUBDOMAIN="${SUBDOMAIN:-finance}"
EXPECTED_ACCOUNT_ID="${EXPECTED_ACCOUNT_ID:-}"

echo "[DEBUG] AWS_REGION: $AWS_REGION"
echo "[DEBUG] PROJECT: $PROJECT"
echo "[DEBUG] ENVIRONMENT: $ENVIRONMENT"
echo "[DEBUG] ZAPPA_PROJECT: $ZAPPA_PROJECT"
echo "[DEBUG] ZAPPA_STAGE: $ZAPPA_STAGE"
echo "[DEBUG] DOMAIN_NAME: $DOMAIN_NAME"
echo "[DEBUG] SUBDOMAIN: $SUBDOMAIN"

# ==============================================================================
# Usage & Help Function
# ==============================================================================
usage() {
  cat <<'EOF'
================================================================================
AWS Resource Cleanup Utility (Verbose)
================================================================================
Inventory and permanently delete AWS resources created by this repository.

Usage: scripts/cleanup_aws_resources.sh [options]

Options:
  --region REGION              AWS region (default: ap-south-1)
  --project NAME               Terraform project prefix (default: finance-dash)
  --environment NAME           Environment suffix (default: prod)
  --zappa-project NAME         Zappa project name (default: portfolio)
  --zappa-stage NAME           Zappa stage (default: production)
  --domain DOMAIN              Route 53 zone (default: karynxt.xyz)
  --subdomain NAME             Custom-domain prefix (default: finance)
  --account-id ID              Refuse to run against any other AWS account
  --help                       Show this help
================================================================================
EOF
}

# ==============================================================================
# Parse Command-Line Arguments
# ==============================================================================
echo "[INFO] Parsing command-line arguments..."
while (($#)); do
  case "$1" in
    --region) AWS_REGION="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --environment) ENVIRONMENT="$2"; shift 2 ;;
    --zappa-project) ZAPPA_PROJECT="$2"; shift 2 ;;
    --zappa-stage) ZAPPA_STAGE="$2"; shift 2 ;;
    --domain) DOMAIN_NAME="$2"; shift 2 ;;
    --subdomain) SUBDOMAIN="$2"; shift 2 ;;
    --account-id) EXPECTED_ACCOUNT_ID="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "[ERROR] Unknown argument: $1"; usage; exit 1 ;;
  esac
done

# ==============================================================================
# Pre-flight Checks
# ==============================================================================
echo "[INFO] Initiating pre-flight checks..."

if ! command -v aws >/dev/null 2>&1; then
  echo "[ERROR] AWS CLI is not installed or not in PATH. Please install it first."
  exit 1
fi

echo "[INFO] Fetching current AWS Caller Identity..."
CURRENT_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "[SUCCESS] Authenticated as AWS Account ID: $CURRENT_ACCOUNT_ID"

if [[ -n "$EXPECTED_ACCOUNT_ID" && "$CURRENT_ACCOUNT_ID" != "$EXPECTED_ACCOUNT_ID" ]]; then
  echo "[FATAL] Account ID mismatch!"
  echo "        Expected: $EXPECTED_ACCOUNT_ID"
  echo "        Actual:   $CURRENT_ACCOUNT_ID"
  exit 1
fi

# ==============================================================================
# Resource Discovery (Inventory Phase)
# ==============================================================================
echo ""
echo "================================================================================"
echo " PHASE 1: DISCOVERY & INVENTORY"
echo "================================================================================"
echo "Scanning AWS Account ($CURRENT_ACCOUNT_ID) in region $AWS_REGION..."

declare -a RESOURCE_TYPES=()
declare -a RESOURCE_IDS=()
declare -a DELETE_ACTIONS=()

add_to_inventory() {
  local type="$1"
  local id="$2"
  local action="$3"
  echo "[DISCOVERED] -> Type: $type | Identifier: $id"
  RESOURCE_TYPES+=("$type")
  RESOURCE_IDS+=("$id")
  DELETE_ACTIONS+=("$action")
}

# Safely construct the prefixes
PREFIX_IAM="${PROJECT}-${ENVIRONMENT}-"
PREFIX_S3="${PROJECT}-zappa-"
PREFIX_SECRET="${PROJECT}/"
ZONE_NAME="${DOMAIN_NAME}."

# 1. IAM Roles
echo "[INFO] Searching for IAM Roles matching prefix: ${PREFIX_IAM}..."
for role in $(aws iam list-roles --query 'Roles[?starts_with(RoleName, `'"${PREFIX_IAM}"'`)].RoleName' --output text); do
  add_to_inventory "IAM Role" "$role" "delete_iam_role"
done

# 2. IAM Policies
echo "[INFO] Searching for IAM Policies matching prefix: ${PREFIX_IAM}..."
for policy_arn in $(aws iam list-policies --scope Local --query 'Policies[?starts_with(PolicyName, `'"${PREFIX_IAM}"'`)].Arn' --output text); do
  add_to_inventory "IAM Policy" "$policy_arn" "delete_iam_policy"
done

# 3. S3 Buckets (Explicitly excludes the TF State bucket)
echo "[INFO] Searching for S3 Buckets matching prefix: ${PREFIX_S3}..."
for bucket in $(aws s3api list-buckets --query 'Buckets[?starts_with(Name, `'"${PREFIX_S3}"'`)].Name' --output text); do
  add_to_inventory "S3 Bucket" "$bucket" "delete_s3_bucket"
done

# 4. Secrets Manager
echo "[INFO] Searching for Secrets Manager secrets matching prefix: ${PREFIX_SECRET}..."
for secret in $(aws secretsmanager list-secrets --region "$AWS_REGION" --query 'SecretList[?starts_with(Name, `'"${PREFIX_SECRET}"'`)].Name' --output text); do
  add_to_inventory "Secret" "$secret" "delete_secret"
done

# 5. Route 53
echo "[INFO] Searching for Route 53 Hosted Zones matching domain: ${DOMAIN_NAME}..."
for zone_id in $(aws route53 list-hosted-zones --query 'HostedZones[?Name==`'"${ZONE_NAME}"'`].Id' --output text | sed 's#/hostedzone/##'); do
  add_to_inventory "Hosted Zone" "$zone_id" "delete_hosted_zone"
done

# ==============================================================================
# Inventory Assessment & User Confirmation
# ==============================================================================
echo ""
echo "================================================================================"
echo " INVENTORY COMPLETE"
echo "================================================================================"
if [ ${#RESOURCE_IDS[@]} -eq 0 ]; then
  echo "[INFO] No resources found matching the specified patterns. Nothing to delete."
  exit 0
fi

echo "[WARNING] The following resources have been identified for PERMANENT DELETION:"
for index in "${!RESOURCE_IDS[@]}"; do
  printf "  %3d. %-25s : %s\n" "$((index + 1))" "${RESOURCE_TYPES[$index]}" "${RESOURCE_IDS[$index]}"
done

echo ""
echo "⚠️  DANGER ZONE: This action is irreversible."
read -rp "Type 'DESTROY-${CURRENT_ACCOUNT_ID}' to confirm: " CONFIRMATION

if [ "$CONFIRMATION" != "DESTROY-${CURRENT_ACCOUNT_ID}" ]; then
  echo "[ABORT] Confirmation string did not match. Exiting safely."
  exit 1
fi

# ==============================================================================
# Helper Deletion Functions
# ==============================================================================

delete_iam_role() {
  local role_name="$1"
  echo "[ACTION] Detaching all policies from IAM Role: $role_name..."
  for policy in $(aws iam list-attached-role-policies --role-name "$role_name" --query 'AttachedPolicies[*].PolicyArn' --output text); do
    echo "         -> Detaching policy: $policy"
    aws iam detach-role-policy --role-name "$role_name" --policy-arn "$policy" || echo "[WARN] Failed to detach $policy"
  done

  echo "[ACTION] Deleting inline policies from IAM Role: $role_name..."
  for inline in $(aws iam list-role-policies --role-name "$role_name" --query 'PolicyNames' --output text); do
    echo "         -> Deleting inline policy: $inline"
    aws iam delete-role-policy --role-name "$role_name" --policy-name "$inline" || echo "[WARN] Failed to delete inline policy $inline"
  done

  echo "[ACTION] Deleting IAM Role: $role_name..."
  aws iam delete-role --role-name "$role_name"
  echo "[SUCCESS] Role $role_name deleted."
}

delete_iam_policy() {
  local policy_arn="$1"
  echo "[ACTION] Fetching non-default versions for policy: $policy_arn..."
  
  while read -r version_id; do
    if [ -n "$version_id" ]; then
      echo "         -> Deleting non-default policy version: $version_id"
      aws iam delete-policy-version --policy-arn "$policy_arn" --version-id "$version_id" || echo "[WARN] Could not delete version $version_id"
    fi
  done < <(aws iam list-policy-versions --policy-arn "$policy_arn" --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text | tr '\t' '\n')
  
  echo "[ACTION] Deleting IAM Policy: $policy_arn..."
  aws iam delete-policy --policy-arn "$policy_arn"
  echo "[SUCCESS] Policy $policy_arn deleted."
}

delete_s3_bucket() {
  local bucket_name="$1"
  echo "[ACTION] Emptying S3 Bucket completely: s3://$bucket_name..."
  
  # 1. Standard recursive delete (handles unversioned files)
  aws s3 rm "s3://$bucket_name" --recursive > /dev/null 2>&1 || true

  # 2. Safely fetch and delete any remaining versions
  local versions
  versions=$(aws s3api list-object-versions --bucket "$bucket_name" --query 'Versions[].{Key:Key,VersionId:VersionId}' --output json 2>/dev/null || echo "null")
  if [[ "$versions" != "null" && "$versions" != "[]" ]]; then
    echo "         -> Cleaning up hidden object versions..."
    echo "{\"Objects\": $versions}" > /tmp/s3_versions_delete.json
    aws s3api delete-objects --bucket "$bucket_name" --delete file:///tmp/s3_versions_delete.json > /dev/null 2>&1 || true
  fi

  # 3. Safely fetch and delete any leftover delete markers
  local markers
  markers=$(aws s3api list-object-versions --bucket "$bucket_name" --query 'DeleteMarkers[].{Key:Key,VersionId:VersionId}' --output json 2>/dev/null || echo "null")
  if [[ "$markers" != "null" && "$markers" != "[]" ]]; then
    echo "         -> Cleaning up delete markers..."
    echo "{\"Objects\": $markers}" > /tmp/s3_markers_delete.json
    aws s3api delete-objects --bucket "$bucket_name" --delete file:///tmp/s3_markers_delete.json > /dev/null 2>&1 || true
  fi
    
  echo "[ACTION] Deleting S3 Bucket: $bucket_name..."
  aws s3 rb "s3://$bucket_name" --force
  echo "[SUCCESS] Bucket $bucket_name deleted."
}

delete_secret() {
  local secret_name="$1"
  echo "[ACTION] Scheduling Secret for immediate deletion (7-day window): $secret_name..."
  aws secretsmanager delete-secret --secret-id "$secret_name" --recovery-window-in-days 7 --region "$AWS_REGION" > /dev/null 2>&1 || true
  echo "[SUCCESS] Secret $secret_name scheduled for deletion (or already deleting)."
}

delete_hosted_zone() {
  local zone_id="$1"
  echo "[ACTION] Evaluating Hosted Zone records for zone ID: $zone_id..."
  
  local change_batch
  change_batch="$(aws route53 list-resource-record-sets --hosted-zone-id "$zone_id" --output json --query '{Changes: ResourceRecordSets[?Type!=`NS` && Type!=`SOA`].{Action:`DELETE`,ResourceRecordSet:@}}')"
  
  if [[ "$change_batch" != *'"Changes": []'* && -n "$change_batch" ]]; then
    echo "         -> Deleting non-essential DNS records..."
    local change_id
    change_id="$(aws route53 change-resource-record-sets --hosted-zone-id "$zone_id" --change-batch "$change_batch" --query ChangeInfo.Id --output text)"
    
    echo "         -> Waiting for DNS changes to propagate (ID: $change_id)..."
    aws route53 wait resource-record-sets-changed --id "$change_id"
  fi
  
  echo "[ACTION] Deleting Route 53 Hosted Zone: $zone_id..."
  aws route53 delete-hosted-zone --id "$zone_id"
  echo "[SUCCESS] Hosted Zone $zone_id deleted."
}

# ==============================================================================
# Execution Phase
# ==============================================================================
echo ""
echo "================================================================================"
echo " PHASE 2: EXECUTING DELETIONS"
echo "================================================================================"

failures=0
for index in "${!RESOURCE_IDS[@]}"; do
  func_name="${DELETE_ACTIONS[$index]}"
  res_id="${RESOURCE_IDS[$index]}"
  res_type="${RESOURCE_TYPES[$index]}"
  
  printf "\n[%d/%d] Attempting to delete %s: %s\n" "$((index + 1))" "${#RESOURCE_IDS[@]}" "$res_type" "$res_id"
  
  if ! "$func_name" "$res_id"; then
    echo "[ERROR] Failed to delete $res_type: $res_id"
    failures=$((failures + 1))
  fi
done

echo ""
echo "================================================================================"
if [ "$failures" -eq 0 ]; then
  echo "🎉 CLEANUP COMPLETED SUCCESSFULLY. All ${#RESOURCE_IDS[@]} resources removed."
else
  echo "⚠️  CLEANUP FINISHED WITH ERRORS. $failures resources could not be deleted."
  echo "   Scroll up to review the logs and resolve dependencies manually."
fi
echo "================================================================================"