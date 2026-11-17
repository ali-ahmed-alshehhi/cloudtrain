# AWS provider. Every resource gets the three required tags automatically.
# Owners: Hamda + Fatma.
#
# Local practice (no AWS bill): LocalStack — same tool as the app (decisions 0005, 0009).
# See environments/dev/localstack.tfvars.example

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Credentials: real AWS → AWS_PROFILE / IAM role.
  # LocalStack → AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  s3_use_path_style           = var.use_localstack

  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3             = var.localstack_endpoint
      sqs            = var.localstack_endpoint
      ecr            = var.localstack_endpoint
      iam            = var.localstack_endpoint
      sts            = var.localstack_endpoint
      ec2            = var.localstack_endpoint
      rds            = var.localstack_endpoint
      secretsmanager = var.localstack_endpoint
      logs           = var.localstack_endpoint
      cloudwatch     = var.localstack_endpoint
      s3control      = var.localstack_endpoint
    }
  }

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      Owner       = var.owner
    }
  }
}
