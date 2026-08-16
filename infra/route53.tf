resource "aws_route53_zone" "primary" {
  name = var.domain_name
}

# ACM DNS validation records
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.dashboard.domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id = aws_route53_zone.primary.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

# A-record alias → API Gateway custom domain (regional endpoint)
resource "aws_route53_record" "dashboard" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = "${var.subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.dashboard.regional_domain_name
    zone_id                = aws_api_gateway_domain_name.dashboard.regional_zone_id
    evaluate_target_health = false
  }
}