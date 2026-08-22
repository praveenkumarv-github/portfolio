output "regional_domain_name" {
  description = "API Gateway target for the proxied Cloudflare CNAME"
  value       = aws_api_gateway_domain_name.dashboard.regional_domain_name
}