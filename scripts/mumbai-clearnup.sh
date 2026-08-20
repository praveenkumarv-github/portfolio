#!/usr/bin/env bash
set -euo pipefail

REGION="ap-south-1"
ACCOUNT="875636131680"

echo "=========================================="
echo " Finance Dashboard - AWS TEARDOWN"
echo " Region : $REGION"
echo " Account: $ACCOUNT"
echo "=========================================="
echo

# ------------------------------------------------------------
# 1. Validate AWS identity
# ------------------------------------------------------------

CURRENT_ACCOUNT=$(aws sts get-caller-identity \
  --query Account \
  --output text)

if [[ "$CURRENT_ACCOUNT" != "$ACCOUNT" ]]; then
  echo "ERROR: Wrong AWS account!"
  echo "Expected: $ACCOUNT"
  echo "Current : $CURRENT_ACCOUNT"
  exit 1
fi

echo "AWS account validated: $CURRENT_ACCOUNT"
echo

# ------------------------------------------------------------
# 2. Project resources from the resource sheet
# ------------------------------------------------------------

LAMBDA="port-production"

LOG_GROUPS=(
  "/aws/lambda/port-production"
  "/aws/lambda/portfolio-production"
)

VPC_ID="vpc-09acd614a2c1474a1"

SUBNETS=(
  "subnet-0a1ccd8c182d3cbfa"
  "subnet-0d5225ebaa9a53a71"
  "subnet-0ab2c2470b313dc31"
)

ROUTE_TABLE="rtb-086038a8804b4751e"

IGW="igw-0cb6f9620c25ccb9e"

SECURITY_GROUP="sg-03f9375ad00c6c4b3"

NETWORK_ACL="acl-08903b393bdaf01b7"

DHCP_OPTIONS="dopt-00485a92c5ef0a9de"

API_IDS=(
  "j55cxwmn1k"
  "zmw0rzjibg"
  "6l6mieg877"
  "pne3plxamk"
)

CFN_STACK="port-production"

# ------------------------------------------------------------
# 3. Show current resources BEFORE deletion
# ------------------------------------------------------------

echo
echo "========== CURRENT RESOURCES =========="
echo

echo "--- Lambda ---"
aws lambda get-function \
  --function-name "$LAMBDA" \
  --region "$REGION" \
  --query 'Configuration.[FunctionName,Runtime,MemorySize,Timeout]' \
  --output table 2>/dev/null || echo "Lambda already absent"

echo
echo "--- VPC ---"
aws ec2 describe-vpcs \
  --vpc-ids "$VPC_ID" \
  --region "$REGION" \
  --query 'Vpcs[].{VPC:VpcId,CIDR:CidrBlock,State:State}' \
  --output table 2>/dev/null || echo "VPC already absent"

echo
echo "--- CloudFormation ---"
aws cloudformation describe-stacks \
  --stack-name "$CFN_STACK" \
  --region "$REGION" \
  --query 'Stacks[].{Stack:StackName,Status:StackStatus}' \
  --output table 2>/dev/null || echo "CloudFormation stack already absent"

echo
echo "--- API Gateway ---"
for API_ID in "${API_IDS[@]}"; do
  aws apigateway get-rest-api \
    --rest-api-id "$API_ID" \
    --region "$REGION" \
    --query '[id,name]' \
    --output text 2>/dev/null || true
done

# ------------------------------------------------------------
# 4. FINAL APPROVAL
# ------------------------------------------------------------

echo
echo "=========================================="
echo " WARNING: DESTRUCTIVE OPERATION"
echo "=========================================="
echo
echo "The following project resources will be"
echo "deleted where they still exist:"
echo
echo "  Lambda       : $LAMBDA"
echo "  CFN stack    : $CFN_STACK"
echo "  VPC          : $VPC_ID"
echo "  Subnets      : ${SUBNETS[*]}"
echo "  Route table  : $ROUTE_TABLE"
echo "  Internet GW  : $IGW"
echo "  Security grp : $SECURITY_GROUP"
echo "  Network ACL  : $NETWORK_ACL"
echo "  DHCP options : $DHCP_OPTIONS"
echo "  API Gateway  : ${API_IDS[*]}"
echo "  Log groups   : ${LOG_GROUPS[*]}"
echo
echo "AWS DEFAULT/SHARED RESOURCES (AND TF STATE BUCKET) WILL NOT BE TOUCHED."
echo

read -r -p 'Type DELETE to continue: ' APPROVAL

if [[ "$APPROVAL" != "DELETE" ]]; then
  echo
  echo "ABORTED. No resources were deleted."
  exit 0
fi

echo
echo "Approval received. Starting teardown..."
echo

# ------------------------------------------------------------
# 5. CloudFormation stack
# ------------------------------------------------------------

echo ">>> Deleting CloudFormation stack..."

aws cloudformation delete-stack \
  --stack-name "$CFN_STACK" \
  --region "$REGION" 2>/dev/null || true

aws cloudformation wait stack-delete-complete \
  --stack-name "$CFN_STACK" \
  --region "$REGION" 2>/dev/null || true

echo ">>> CloudFormation deletion completed/absent"

# ------------------------------------------------------------
# 6. API Gateway
# ------------------------------------------------------------

echo
echo ">>> Deleting API Gateway APIs..."

for API_ID in "${API_IDS[@]}"; do
  echo "Deleting API: $API_ID"

  aws apigateway delete-rest-api \
    --rest-api-id "$API_ID" \
    --region "$REGION" 2>/dev/null || true
done

# ------------------------------------------------------------
# 7. Lambda
# ------------------------------------------------------------

echo
echo ">>> Deleting Lambda..."

aws lambda delete-function \
  --function-name "$LAMBDA" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 8. CloudWatch Logs
# ------------------------------------------------------------

echo
echo ">>> Deleting CloudWatch log groups..."

for LOG_GROUP in "${LOG_GROUPS[@]}"; do
  echo "Deleting: $LOG_GROUP"

  aws logs delete-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" 2>/dev/null || true
done

# ------------------------------------------------------------
# 9. Detach Internet Gateway
# ------------------------------------------------------------

echo
echo ">>> Detaching Internet Gateway..."

aws ec2 detach-internet-gateway \
  --internet-gateway-id "$IGW" \
  --vpc-id "$VPC_ID" \
  --region "$REGION" 2>/dev/null || true

echo ">>> Deleting Internet Gateway..."

aws ec2 delete-internet-gateway \
  --internet-gateway-id "$IGW" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 10. Delete subnets
# ------------------------------------------------------------

echo
echo ">>> Deleting subnets..."

for SUBNET in "${SUBNETS[@]}"; do
  echo "Deleting subnet: $SUBNET"

  aws ec2 delete-subnet \
    --subnet-id "$SUBNET" \
    --region "$REGION" 2>/dev/null || true
done

# ------------------------------------------------------------
# 11. Delete route table
# ------------------------------------------------------------

echo
echo ">>> Deleting route table..."

aws ec2 delete-route-table \
  --route-table-id "$ROUTE_TABLE" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 12. Delete security group
# ------------------------------------------------------------

echo
echo ">>> Deleting security group..."

aws ec2 delete-security-group \
  --group-id "$SECURITY_GROUP" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 13. Delete network ACL
# ------------------------------------------------------------

echo
echo ">>> Deleting network ACL..."

aws ec2 delete-network-acl \
  --network-acl-id "$NETWORK_ACL" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 14. Delete DHCP options
# ------------------------------------------------------------

echo
echo ">>> Deleting DHCP options..."

aws ec2 delete-dhcp-options \
  --dhcp-options-id "$DHCP_OPTIONS" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 15. Delete VPC
# ------------------------------------------------------------

echo
echo ">>> Deleting VPC..."

aws ec2 delete-vpc \
  --vpc-id "$VPC_ID" \
  --region "$REGION" 2>/dev/null || true

# ------------------------------------------------------------
# 16. Final verification
# ------------------------------------------------------------

echo
echo "=========================================="
echo " FINAL VERIFICATION"
echo "=========================================="

echo
echo "--- VPC ---"
aws ec2 describe-vpcs \
  --vpc-ids "$VPC_ID" \
  --region "$REGION" \
  --output table 2>/dev/null || echo "VPC deleted"

echo
echo "--- Lambda ---"
aws lambda get-function \
  --function-name "$LAMBDA" \
  --region "$REGION" \
  --output table 2>/dev/null || echo "Lambda deleted"

echo
echo "=========================================="
echo " TEARDOWN COMPLETE"
echo "=========================================="