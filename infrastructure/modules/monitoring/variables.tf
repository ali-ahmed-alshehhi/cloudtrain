variable "environment" {
  type = string
}

variable "services" {
  description = "One log group per ECS service, as /cloudtrain/<env>/<service> (the path the execution role may write to, #129)."
  type        = list(string)
  default = [
    "gateway",
    "portal",
    "project-service",
    "dataset-service",
    "job-service",
    "scheduler",
    "model-registry",
    "inference-service",
    "mlflow",
  ]
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps service logs. Short in dev: logs are for debugging, not records."
  type        = number
  default     = 14
}

variable "training_jobs_dlq_arn" {
  type = string
}

variable "job_events_queue_arn" {
  type = string
}

variable "alb_arn_suffix" {
  description = "The public load balancer's arn_suffix (application-services, #36). null = no server-errors alarm yet."
  type        = string
  default     = null
}

variable "alarm_actions" {
  description = "Where alarms notify (for example an SNS topic ARN). Empty = alarms show in CloudWatch only."
  type        = list(string)
  default     = []
}
