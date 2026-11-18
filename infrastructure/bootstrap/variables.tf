# Inputs for the remote-state bootstrap. Values live in a *.tfvars file (git-ignored);
# commit only the *.example file. Owners: Hamda + Fatma.

variable "project" {
  description = "Project tag on every resource."
  type        = string
  default     = "cloudtrain"
}

variable "environment" {
  description = "Environment tag. The one state bucket serves dev and staging, each under its own key."
  type        = string
  default     = "shared"
}

variable "owner" {
  description = "Owner tag on every resource (who to ask about it)."
  type        = string
}

variable "aws_region" {
  description = "AWS region of the state bucket. Must match `region` in the backend .hcl file."
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

variable "state_bucket_name" {
  description = "S3 bucket for Terraform state. On real AWS it must be globally unique."
  type        = string
}

variable "enforce_tls" {
  description = "Attach the bucket policy that refuses non-HTTPS requests."
  type        = bool
  default     = true
}

variable "noncurrent_version_days" {
  description = "How many days old state versions are kept before S3 removes them."
  type        = number
  default     = 90
}
