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
