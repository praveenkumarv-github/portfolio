variable "aws_region" {
  description = "AWS region for the API Gateway custom domain"
  type        = string
  default     = "ap-south-1"
}

variable "domain_name" {
  description = "Root domain managed by Cloudflare"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the dashboard"
  type        = string
  default     = "finance"
}

variable "project" {
  description = "Short name prefix applied to resource tags"
  type        = string
  default     = "finance-dash"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "prod"
}

variable "acm_certificate_arn" {
  description = "Certificate ARN created by the Phase 1 Terraform stack"
  type        = string
}

variable "zappa_api_gateway_id" {
  description = "REST API ID created by Zappa"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{10,}$", var.zappa_api_gateway_id))
    error_message = "zappa_api_gateway_id must be a valid API Gateway REST API ID."
  }
}

variable "zappa_stage_name" {
  description = "Zappa stage name"
  type        = string
  default     = "production"
}