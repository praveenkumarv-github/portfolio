variable "aws_region" {
  description = "AWS region for Lambda and all regional resources"
  type        = string
  default     = "ap-south-1"
}

variable "domain_name" {
  description = "Root domain you purchased (e.g. example.com)"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the dashboard (e.g. finance → finance.example.com)"
  type        = string
  default     = "finance"
}

variable "project" {
  description = "Short name prefix applied to all resource names"
  type        = string
  default     = "finance-dash"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "prod"
}

# ── Phase-2 variables — fill after running `zappa deploy` ─────────────────
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
