locals {
  # Allows wildcard branch matching so any branch from your repo can deploy
  github_sub = "repo:${var.github_owner}/${var.github_repo}:*"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_oidc_role ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
    "1b511abead59c6ce207077c0bf0e0043b1382612"
  ]
}

data "aws_iam_policy_document" "github_actions_assume" {
  count = var.enable_github_oidc_role ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:*"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  count = var.enable_github_oidc_role ? 1 : 0

  name               = "${var.project}-github-actions-deploy-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume[0].json
}

data "aws_iam_policy_document" "github_actions_deploy" {
  count = var.enable_github_oidc_role ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "acm:*",
      "apigateway:*",
      "cloudformation:*",
      "events:*",
      "iam:GetRole",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:PassRole",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
      "lambda:*",
      "logs:*",
      "route53:*",
      "s3:*",
      "secretsmanager:*",
      "sts:GetCallerIdentity",
      "tag:GetResources",
      "tag:TagResources",
      "tag:UntagResources"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_actions_deploy" {
  count = var.enable_github_oidc_role ? 1 : 0

  name        = "${var.project}-github-actions-deploy-${var.environment}"
  description = "Permissions for GitHub Actions to deploy Lambda and manage infrastructure"
  policy      = data.aws_iam_policy_document.github_actions_deploy[0].json
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  count = var.enable_github_oidc_role ? 1 : 0

  role       = aws_iam_role.github_actions_deploy[0].name
  policy_arn = aws_iam_policy.github_actions_deploy[0].arn
}
