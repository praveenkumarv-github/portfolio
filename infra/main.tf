terraform {
  required_version = ">= 1.5"
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

resource "aws_acm_certificate_validation" "dashboard" {
  certificate_arn         = aws_acm_certificate.dashboard.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

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
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*:*",
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

# (The Zappa deploy policy from your file remains the same. 
# Omitted here for brevity, but you should keep the zappa_deploy blocks if you deploy via CI/CD).

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