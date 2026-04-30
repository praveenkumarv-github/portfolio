# ACM certificate — REGIONAL, same region as Lambda + API Gateway.
# DNS validation uses the Route 53 zone created in route53.tf.

resource "aws_acm_certificate" "dashboard" {
  domain_name       = "${var.subdomain}.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "dashboard" {
  certificate_arn         = aws_acm_certificate.dashboard.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
