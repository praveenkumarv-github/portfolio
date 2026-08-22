terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # These tags will be automatically applied to ALL resources
  # (Lambda, S3, API Gateway, IAM Roles, Secrets Manager, etc.)
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      purpose     = "fin-dashboard"
    }
  }
}

data "aws_caller_identity" "current" {}


resource "aws_acm_certificate" "dashboard" {
  domain_name       = "${var.subdomain}.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project}-lambda-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "lambda_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.zappa_project_name}-*:*",
    ]
  }
}

resource "aws_iam_policy" "lambda_logs" {
  name   = "${var.project}-lambda-logs-${var.environment}"
  policy = data.aws_iam_policy_document.lambda_logs.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_logs.arn
}

data "aws_iam_policy_document" "lambda_secrets" {
  statement {
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.google_sa.arn,
    ]
  }
}

resource "aws_iam_policy" "lambda_secrets" {
  name   = "${var.project}-lambda-secrets-${var.environment}"
  policy = data.aws_iam_policy_document.lambda_secrets.json
}

resource "aws_iam_role_policy_attachment" "lambda_secrets" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_secrets.arn
}

resource "aws_s3_bucket" "deploy" {
  bucket = "${var.project}-zappa-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket = aws_s3_bucket.deploy.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "deploy" {
  bucket = aws_s3_bucket.deploy.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

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