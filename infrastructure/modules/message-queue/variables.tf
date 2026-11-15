variable "training_jobs_queue_name" {
  type    = string
  default = "training-jobs"
}

variable "training_jobs_dlq_name" {
  type    = string
  default = "training-jobs-dlq"
}

variable "job_events_queue_name" {
  type    = string
  default = "job-events"
}

variable "visibility_timeout_seconds" {
  description = "Must cover scheduling time (matches .env SQS_VISIBILITY_TIMEOUT_SECONDS)."
  type        = number
  default     = 300
}

variable "max_receive_count" {
  description = "Failures before a message moves to the DLQ."
  type        = number
  default     = 3
}
