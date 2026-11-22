variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  description = "Public ALB security group (from modules/security). Empty string = use the VPC default group (emulator)."
  type        = string
  default     = ""
}

variable "services_security_group_id" {
  description = "ECS tasks security group. Empty string = use the VPC default group (emulator)."
  type        = string
  default     = ""
}

variable "default_security_group_id" {
  description = "VPC default security group, used when our own groups are skipped (emulator)."
  type        = string
}

variable "execution_role_arn" {
  description = "Shared ECS task execution role (modules/iam ecs_task_execution)."
  type        = string
}

variable "task_role_arns" {
  description = "Per service: task role ARN from modules/service-roles."
  type        = map(string)
}

variable "ecr_repository_urls" {
  description = "Per service: ECR repository URL (no tag)."
  type        = map(string)
}

variable "image_tag" {
  description = "Image tag to deploy (commit SHA from images.yml). Not 'latest' (ECR is immutable)."
  type        = string
  default     = "bootstrap"
}

variable "desired_count" {
  description = "How many tasks per service. 0 = define services without starting tasks (emulator / no images yet)."
  type        = number
  default     = 0
}

variable "log_group_names" {
  description = "Per service: CloudWatch log group name from monitoring. Empty = create /cloudtrain/<env>/<service> here."
  type        = map(string)
  default     = {}
}

variable "database_secret_names" {
  description = "Per service: Secrets Manager name for DATABASE_URL (null = no database). From service-roles."
  type        = map(string)
  default     = {}
}

variable "datasets_bucket" {
  type = string
}

variable "artifacts_bucket" {
  type = string
}

variable "training_jobs_queue_url" {
  type = string
}

variable "training_jobs_dlq_url" {
  type = string
}

variable "job_events_queue_url" {
  type = string
}

variable "jwt_issuer" {
  type    = string
  default = ""
}

variable "jwt_audience" {
  type    = string
  default = ""
}

variable "jwt_jwks_url" {
  type    = string
  default = ""
}

variable "worker_urls_json" {
  description = "JSON map of machine type to worker URL for TRAINING_WORKER_URLS (Fatma). Empty until worker LBs land."
  type        = string
  default     = ""
}

variable "enable_service_discovery" {
  description = "Private DNS for service-to-service URLs. Turn off if the stand-in has no Cloud Map."
  type        = bool
  default     = true
}
