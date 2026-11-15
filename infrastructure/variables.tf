# Shared input variables. Values per environment live in environments/<env>/
# (*.tfvars files are git-ignored; commit only non-secret *.example files).
# Owners: Hamda + Fatma.

variable "project" {
  description = "Project tag on every resource."
  type        = string
  default     = "cloudtrain"
}

variable "environment" {
  description = "dev or staging."
  type        = string

  validation {
    condition     = contains(["dev", "staging"], var.environment)
    error_message = "environment must be dev or staging."
  }
}

variable "owner" {
  description = "Owner tag on every resource (who to ask about it)."
  type        = string
}

variable "aws_region" {
  description = "AWS region, decided with the instructors (see docs/OPEN_DECISIONS.md)."
  type        = string
}

variable "use_localstack" {
  description = "Point Terraform at LocalStack (same tool as the app — decisions 0005, 0007)."
  type        = bool
  default     = false
}

variable "localstack_endpoint" {
  description = "LocalStack edge endpoint when use_localstack=true."
  type        = string
  default     = "http://localhost:4568"
}

variable "datasets_bucket_name" {
  description = "S3 datasets bucket. Local: datasets. Real AWS: must be globally unique."
  type        = string
}

variable "artifacts_bucket_name" {
  description = "S3 artifacts bucket. Local: artifacts. Real AWS: must be globally unique."
  type        = string
}

variable "sqs_visibility_timeout_seconds" {
  type    = number
  default = 300
}

variable "sqs_max_receive_count" {
  type    = number
  default = 3
}

variable "enable_networking" {
  description = "Create VPC/subnets. Off for LocalStack practice; on for real AWS."
  type        = bool
  default     = true
}

variable "enable_container_registry" {
  description = "Create ECR repositories. Off for LocalStack practice; on for real AWS."
  type        = bool
  default     = true
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}
