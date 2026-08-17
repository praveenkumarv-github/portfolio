output "lambda_role_arn" {
  description = "Paste as role_arn in zappa_settings.json"
  value       = aws_iam_role.lambda_exec.arn
}

output "s3_bucket" {
  description = "Paste as s3_bucket in zappa_settings.json"
  value       = aws_s3_bucket.deploy.bucket
}

output "route53_nameservers" {
  description = "IMPORTANT: set these as NS records at your domain registrar"
  value       = aws_route53_zone.primary.name_servers
}

output "github_actions_role_arn" {
  description = "Role ARN for GitHub Actions OIDC deploy workflow"
  value       = try(aws_iam_role.github_actions_deploy[0].arn, "")
}