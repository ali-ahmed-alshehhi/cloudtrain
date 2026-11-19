variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "datasets_bucket_arn" {
  type = string
}

variable "artifacts_bucket_arn" {
  type = string
}

variable "training_jobs_queue_arn" {
  type = string
}

variable "training_jobs_dlq_arn" {
  type = string
}

variable "job_events_queue_arn" {
  type = string
}
