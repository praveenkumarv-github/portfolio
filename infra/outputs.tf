output "lambda_role_arn" {
  description = "Paste as role_arn in zappa_settings.json"
  value       = aws_iam_role.lambda_exec.arn
}

output "s3_bucket" {
  description = "Paste as s3_bucket in zappa_settings.json"
  value       = aws_s3_bucket.deploy.bucket
}

output "secret_arn" {
  description = "Secrets Manager ARN — run `aws secretsmanager put-secret-value` to load the SA JSON"
  value       = aws_secretsmanager_secret.google_sa.arn
}

output "zappa_deploy_policy_arn" {
  description = "Attach to the IAM user/role that runs `zappa deploy`"
  value       = aws_iam_policy.zappa_deploy.arn
}

output "dashboard_url" {
  description = "Final dashboard URL (live after phase-2 apply)"
  value       = "https://${var.subdomain}.${var.domain_name}"
}

output "route53_nameservers" {
  description = "IMPORTANT: set these as NS records at your domain registrar"
  value       = aws_route53_zone.primary.name_servers
}
