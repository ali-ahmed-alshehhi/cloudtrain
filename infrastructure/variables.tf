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

variable "use_emulator" {
  description = "Point Terraform at the AWS Emulator instead of a real AWS account (decision 0011)."
  type        = bool
  default     = false
}

variable "emulator_endpoint" {
  description = "AWS Emulator HTTPS endpoint when use_emulator=true."
  type        = string
  default     = "https://127.0.0.1:9297"
}

variable "use_localstack" {
  description = "Point Terraform at LocalStack (same tool as the app — decisions 0005, 0009)."
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

variable "enable_security_groups" {
  description = <<-EOT
    Create our own security groups (ALB, services, workers, database). Off on the AWS Emulator:
    its RevokeSecurityGroupEgress does not match the all-protocols rule Terraform removes right
    after creating a group (ports 0-0), so every aws_security_group fails there. The database
    then uses the VPC's locked-down default group. See infrastructure/README.md.
  EOT
  type        = bool
  default     = true
}

variable "enable_container_registry" {
  description = "Create ECR repositories. Off for LocalStack practice; on for real AWS."
  type        = bool
  default     = true
}

variable "enable_database" {
  description = "Create RDS PostgreSQL. Requires networking. Off for LocalStack practice."
  type        = bool
  default     = false
}

variable "enable_identity" {
  description = "Create Cognito user pool + portal client + role groups (decision 0006). On for emulator/real AWS; off for LocalStack."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "enable_training_compute" {
  description = "Create the worker IAM role and the GPU Auto Scaling group. Requires networking."
  type        = bool
  default     = false
}

variable "enable_ecs_roles" {
  description = "Create the ECS task execution role and the GitHub OIDC deploy role (modules/iam/ecs.tf)."
  type        = bool
  default     = false
}

variable "gpu_instance_type" {
  description = "GPU worker machine type, a key of contracts/pricing.yaml."
  type        = string
  default     = "g4dn.xlarge"
}

variable "worker_ami_id" {
  description = "Machine image for workers (Deep Learning Base GPU AMI on real AWS; any ami-... on the emulator)."
  type        = string
  default     = "ami-00000000"
}

variable "worker_desired_capacity" {
  description = "How many GPU workers run. Change it and re-apply to scale (demo 4). 0 = none."
  type        = number
  default     = 0
}

variable "worker_max_size" {
  description = "Upper limit of GPU workers."
  type        = number
  default     = 2
}

variable "enable_service_roles" {
  description = "Create one least-privilege task role per service. Needed by ECS (#36)."
  type        = bool
  default     = false
}

variable "enable_application_services" {
  description = "Create the ECS Fargate cluster, services and public ALB (#36)."
  type        = bool
  default     = false
}

variable "ecs_image_tag" {
  description = "Container image tag for ECS task definitions (commit SHA from images.yml)."
  type        = string
  default     = "bootstrap"
}

variable "ecs_desired_count" {
  description = "Desired Fargate tasks per service. 0 on the emulator until images exist in ECR."
  type        = number
  default     = 0
}

variable "enable_ecs_service_discovery" {
  description = "Private DNS for service-to-service calls. Set false if the stand-in has no Cloud Map."
  type        = bool
  default     = true
}

variable "worker_urls_json" {
  description = "JSON map of machine type to worker URL (Fatma worker LBs). Passed to scheduler as TRAINING_WORKER_URLS."
  type        = string
  default     = ""
}
