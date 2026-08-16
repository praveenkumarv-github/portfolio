# Secrets Manager — Google Service Account JSON
#
# After `terraform apply`, upload the actual JSON:
#
#   aws secretsmanager put-secret-value \
#     --secret-id finance-dash/google-service-account \
#     --secret-string file://service-account-key.json
#
# Then copy the JSON value into GOOGLE_SERVICE_ACCOUNT_JSON
# inside zappa_settings.json (as a single-line string) before deploying.

resource "aws_secretsmanager_secret" "google_sa" {
  name                    = "${var.project}/google-service-account"
  description             = "Google Service Account JSON — private Google Sheets access"
  recovery_window_in_days = 7
}

# Placeholder version — Terraform manages the secret shell only.
# The actual key value is loaded outside Terraform (see above).
resource "aws_secretsmanager_secret_version" "google_sa_placeholder" {
  secret_id     = aws_secretsmanager_secret.google_sa.id
  secret_string = jsonencode({ note = "replace-via-aws-cli" })

  lifecycle {
    ignore_changes = [secret_string] # managed outside Terraform
  }
}
