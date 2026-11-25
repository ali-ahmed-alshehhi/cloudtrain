variable "datasets_bucket_name" {
  description = "S3 bucket for datasets (logical name locally: datasets)."
  type        = string
}

variable "artifacts_bucket_name" {
  description = "S3 bucket for checkpoints and models (logical name locally: artifacts)."
  type        = string
}
