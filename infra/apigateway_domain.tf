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