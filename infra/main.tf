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
  # (Lambda, S3, API Gateway, IAM roles, etc.)
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

resource "aws_s3_bucket" "deploy" {
  bucket = "${var.project}-zappa-${var.environment}"
}

resource "aws_s3_bucket_versioning" "deploy" {
  bucket = aws_s3_bucket.deploy.id

  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_iam_policy_document" "lambda_slim_handler" {
  statement {
    sid    = "AllowLambdaSlimHandlerDownload"
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "${aws_s3_bucket.deploy.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_slim_handler" {
  name        = "${var.project}-lambda-slim-handler-${var.environment}"
  description = "Allows Lambda execution role to fetch Zappa slim handler code package"
  policy      = data.aws_iam_policy_document.lambda_slim_handler.json
}

resource "aws_iam_role_policy_attachment" "lambda_slim_handler" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_slim_handler.arn
}

data "aws_iam_policy_document" "lambda_net_worth" {
  statement {
    sid       = "ListNetWorthHistory"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.deploy.arn]

    condition {
      test     = "StringEquals"
      variable = "s3:prefix"
      values   = ["net-worth/history/"]
    }
  }

  statement {
    sid       = "WriteNetWorthHistory"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.deploy.arn}/net-worth/history/*"]
  }

  statement {
    sid     = "ReadDeployBucketArtifactsAndHistory"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.deploy.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_net_worth" {
  name   = "${var.project}-lambda-net-worth-${var.environment}"
  policy = data.aws_iam_policy_document.lambda_net_worth.json
}

resource "aws_iam_role_policy_attachment" "lambda_net_worth" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_net_worth.arn
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
