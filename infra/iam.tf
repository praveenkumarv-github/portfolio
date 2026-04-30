# ─── Lambda execution role ───────────────────────────────────────────────────
# Follows least-privilege: only the exact actions Lambda needs at runtime.

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

# ── Policy 1: CloudWatch Logs — scoped to this function's log group ──────────
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

# ── Policy 2: Secrets Manager — only the SA secret ───────────────────────────
# Allows runtime read of the Google Service Account JSON from Secrets Manager.
# (Also used by GOOGLE_SERVICE_ACCOUNT_JSON env var injection at deploy time.)
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

# ─── Zappa deploy policy ─────────────────────────────────────────────────────
# Attach to the IAM user / CI role that runs `zappa deploy / update`.
# NOT attached to the Lambda execution role.

data "aws_iam_policy_document" "zappa_deploy" {
  # Lambda management — scoped to this project's functions only
  statement {
    effect = "Allow"
    actions = [
      "lambda:CreateFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:DeleteFunction",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:InvokeFunction",
      "lambda:ListVersionsByFunction",
      "lambda:PublishVersion",
      "lambda:GetPolicy",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project}-*",
    ]
  }

  # API Gateway — required for Zappa to create/manage the REST API
  statement {
    effect    = "Allow"
    actions   = ["apigateway:*"]
    resources = ["arn:aws:apigateway:${var.aws_region}::/*"]
  }

  # S3 — deploy bucket only
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.deploy.arn,
      "${aws_s3_bucket.deploy.arn}/*",
    ]
  }

  # CloudWatch — create log group during first deploy
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DescribeLogGroups",
      "logs:DeleteLogGroup",
      "logs:DescribeLogStreams",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*",
    ]
  }

  # IAM — PassRole so Zappa assigns the exec role to Lambda
  statement {
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.lambda_exec.arn]
  }
}

resource "aws_iam_policy" "zappa_deploy" {
  name   = "${var.project}-zappa-deploy-${var.environment}"
  policy = data.aws_iam_policy_document.zappa_deploy.json
}
