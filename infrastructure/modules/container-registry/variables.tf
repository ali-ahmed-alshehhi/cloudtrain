variable "repository_names" {
  description = "One ECR repository per service image."
  type        = list(string)
  default = [
    "gateway",
    "project-service",
    "dataset-service",
    "job-service",
    "scheduler",
    "training-worker",
    "model-registry",
    "inference-service",
    "portal",
    "mlflow",
    "job-events-monitor",
  ]
}

variable "environment" {
  type = string
}
