variable "aws_region" {
  description = "AWS region for Lambda and all regional resources"
  type        = string
  default     = "ap-south-1"
}

variable "domain_name" {
  description = "Root domain you purchased (e.g. karynxt.xyz)"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the dashboard (e.g. finance)"
  type        = string
  default     = "finance"
}

variable "project" {
  description = "Short name prefix applied to all resource names"
  type        = string
  default     = "finance-dash"
}

variable "zappa_project_name" {
  description = "Zappa project name used as the Lambda and CloudFormation name prefix"
  type        = string
  default     = "portfolio"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "prod"
}

variable "zappa_api_gateway_id" {
  description = "REST API ID printed by `zappa deploy` (leave empty on first apply)"
  type        = string
  default     = ""
}

variable "zappa_stage_name" {
  description = "Zappa stage name (must match key in zappa_settings.json)"
  type        = string
  default     = "production"
}

variable "enable_github_oidc_role" {
  description = "Create IAM OIDC provider + role for GitHub Actions deployments"
  type        = bool
  default     = true
}

variable "github_owner" {
  description = "GitHub repository owner for OIDC trust policy"
  type        = string
  default     = "praveenkumarv-github"
}

variable "github_repo" {
  description = "GitHub repository name for OIDC trust policy"
  type        = string
  default     = "portfolio"
}

variable "github_branch" {
  description = "GitHub branch name allowed to assume OIDC role"
  type        = string
  default     = "fea-v2"
}