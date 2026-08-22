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

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      purpose     = "fin-dashboard"
    }
  }
}

resource "aws_acm_certificate_validation" "dashboard" {
  certificate_arn = var.acm_certificate_arn
}

resource "aws_api_gateway_domain_name" "dashboard" {
  domain_name              = "${var.subdomain}.${var.domain_name}"
  regional_certificate_arn = aws_acm_certificate_validation.dashboard.certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_base_path_mapping" "dashboard" {
  api_id      = var.zappa_api_gateway_id
  domain_name = aws_api_gateway_domain_name.dashboard.domain_name
  stage_name  = var.zappa_stage_name
}