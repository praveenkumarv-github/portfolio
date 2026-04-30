# API Gateway custom domain + base-path mapping
#
# Phase 1 (first `terraform apply`):
#   - `zappa_api_gateway_id` is empty → mapping is skipped.
#   - Custom domain resource is still created so the CNAME/A record is ready.
#
# Phase 2 (after `zappa deploy`):
#   1. Run: zappa deploy production
#   2. Note the REST API ID from Zappa output.
#   3. Set in terraform.tfvars:
#        zappa_api_gateway_id = "<api-id>"
#   4. Run: terraform apply
#   → mapping is created and custom domain goes live.

resource "aws_api_gateway_domain_name" "dashboard" {
  domain_name              = "${var.subdomain}.${var.domain_name}"
  regional_certificate_arn = aws_acm_certificate_validation.dashboard.certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_base_path_mapping" "dashboard" {
  count = var.zappa_api_gateway_id != "" ? 1 : 0

  api_id      = var.zappa_api_gateway_id
  domain_name = aws_api_gateway_domain_name.dashboard.domain_name
  stage_name  = var.zappa_stage_name
}
