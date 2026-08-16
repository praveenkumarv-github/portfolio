resource "aws_secretsmanager_secret" "google_sa" {
  name                    = "${var.project}/google-service-account"
  description             = "Google Service Account JSON"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "google_sa_placeholder" {
  secret_id     = aws_secretsmanager_secret.google_sa.id
  secret_string = jsonencode({ note = "replace-via-aws-cli" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}