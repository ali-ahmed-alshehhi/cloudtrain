# AWS provider. Every resource gets the three required tags automatically.
# Owners: Hamda + Fatma.
#
# Practice (no AWS bill): official AWS Emulator — see scripts/emulator-up.sh
# and environments/dev/emulator.tfvars.example.
# Docs: https://github.com/aws/aws-emulator

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
  # Emulator → source scripts/emulator-env.sh (uses ~/.aws/emulator/9297/…)
  skip_credentials_validation = var.use_emulator
  skip_metadata_api_check     = var.use_emulator
  skip_requesting_account_id  = var.use_emulator
  s3_use_path_style           = var.use_emulator

  # Emulator serves HTTPS with its own CA; Terraform also reads AWS_CA_BUNDLE
  # from scripts/emulator-env.sh. insecure=true covers SDKs that skip the bundle.
  insecure = var.use_emulator

  dynamic "endpoints" {
    for_each = var.use_emulator ? [1] : []
    content {
      s3             = var.emulator_endpoint
      sqs            = var.emulator_endpoint
      ecr            = var.emulator_endpoint
      iam            = var.emulator_endpoint
      sts            = var.emulator_endpoint
      ec2            = var.emulator_endpoint
      rds            = var.emulator_endpoint
      secretsmanager = var.emulator_endpoint
      logs           = var.emulator_endpoint
      cloudwatch     = var.emulator_endpoint
      s3control      = var.emulator_endpoint
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
