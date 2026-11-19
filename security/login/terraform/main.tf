# Applies the login module (infrastructure/modules/identity) on the AWS Emulator (decision 0011).
# Owner: Salem. Run through ../setup.sh, which sources the emulator settings first.
# State stays on this laptop or CI machine (*.tfstate is git-ignored); it holds no secret.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "emulator_endpoint" {
  type    = string
  default = "https://127.0.0.1:9297"
}

provider "aws" {
  region = var.aws_region

  # Credentials and the emulator's CA certificate come from infrastructure/scripts/emulator-env.sh
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    cognitoidp = var.emulator_endpoint
    sts        = var.emulator_endpoint
  }

  default_tags {
    tags = {
      Project     = "cloudtrain"
      Environment = "dev"
      Owner       = "salem"
    }
  }
}

module "identity" {
  source = "../../../infrastructure/modules/identity"

  environment                = "dev"
  aws_region                 = var.aws_region
  issuer_base_url            = var.emulator_endpoint
  allow_admin_password_login = true
}

output "user_pool_id" {
  value = module.identity.user_pool_id
}

output "portal_client_id" {
  value = module.identity.portal_client_id
}

output "issuer" {
  value = module.identity.issuer
}

output "jwks_url" {
  value = module.identity.jwks_url
}
