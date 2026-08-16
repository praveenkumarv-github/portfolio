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