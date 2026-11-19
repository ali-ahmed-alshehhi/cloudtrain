variable "environment" {
  type = string
}

variable "datasets_bucket_arn" {
  description = "Workers read training data from here."
  type        = string
}

variable "artifacts_bucket_arn" {
  description = "Workers write checkpoints and models here."
  type        = string
}

variable "job_events_queue_arn" {
  description = "Workers report job progress here (send only)."
  type        = string
}

# ---------- ECS roles (ecs.tf, Salem) ----------

variable "enable_ecs_roles" {
  description = "Create the ECS task execution role and the GitHub OIDC deploy role."
  type        = bool
  default     = false
}

variable "aws_region" {
  description = "Region, used to name the log groups and ECS services the roles may touch."
  type        = string
  default     = "us-east-1"
}

variable "ecr_repository_arns" {
  description = "The CloudTrain image repositories. Tasks pull, and the deploy role pushes, only these."
  type        = list(string)
  default     = []
}

variable "secret_arns" {
  description = "Secrets the task definitions inject (e.g. the database master secret). Nothing else is readable."
  type        = list(string)
  default     = []
}

variable "ecs_cluster_name" {
  description = "ECS cluster of the services (#36). The deploy role may update services in this cluster only."
  type        = string
  default     = "dev-cloudtrain"
}

variable "task_role_arns" {
  description = "Per-service task roles (#36) the deploy role may pass to ECS, besides the execution role."
  type        = list(string)
  default     = []
}

variable "github_repository" {
  description = "owner/name of the repository whose main branch and environments may deploy."
  type        = string
  default     = "ali-ahmed-alshehhi/cloudtrain"
}
