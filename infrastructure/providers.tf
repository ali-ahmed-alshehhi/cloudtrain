# AWS provider. Every resource gets the three required tags automatically.
# Owners: Hamda + Fatma.
#
# No AWS account: the AWS Emulator stands in for it (decision 0011).
# See environments/dev/emulator.tfvars.example. LocalStack still works (use_localstack).

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
  # AWS Emulator → `source scripts/emulator-env.sh` (credentials file + CA certificate).
  # LocalStack → AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  skip_credentials_validation = local.practice_aws
  skip_metadata_api_check     = local.practice_aws
  skip_requesting_account_id  = local.practice_aws
  # Both stand-ins answer path-style S3 addresses only (https://127.0.0.1:9297/<bucket>).
  s3_use_path_style = local.practice_aws

  dynamic "endpoints" {
    for_each = local.practice_aws ? [1] : []
    content {
      s3             = local.practice_endpoint
      sqs            = local.practice_endpoint
      ecr            = local.practice_endpoint
      ecs            = local.practice_endpoint
      elbv2          = local.practice_endpoint
      iam            = local.practice_endpoint
      sts            = local.practice_endpoint
      ec2            = local.practice_endpoint
      autoscaling    = local.practice_endpoint
      rds            = local.practice_endpoint
      secretsmanager = local.practice_endpoint
      kms            = local.practice_endpoint
      logs           = local.practice_endpoint
      cloudwatch     = local.practice_endpoint
      s3control      = local.practice_endpoint
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

locals {
  # A stand-in for AWS instead of a real account: the AWS Emulator (decision 0011) or LocalStack.
  practice_aws      = var.use_emulator || var.use_localstack
  practice_endpoint = var.use_emulator ? var.emulator_endpoint : var.localstack_endpoint
}
