output "lambda_role_arn" {
  description = "Paste as role_arn in zappa_settings.json"
  value       = aws_iam_role.lambda_exec.arn
}

output "s3_bucket" {
  description = "Paste as s3_bucket in zappa_settings.json"
  value       = aws_s3_bucket.deploy.bucket
}

output "acm_certificate_arn" {
  description = "ACM certificate consumed by the Phase 2 domain stack"
  value       = aws_acm_certificate.dashboard.arn
}

output "acm_validation_records" {
  description = "DNS records that Phase 2 publishes to Cloudflare before validating ACM"
  value = [
    for option in aws_acm_certificate.dashboard.domain_validation_options : {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  ]
}

output "github_actions_role_arn" {
  description = "Role ARN for GitHub Actions OIDC deploy workflow"
  value       = try(aws_iam_role.github_actions_deploy[0].arn, "")
}