# Shared input variables. Values per environment live in environments/<env>/
# (*.tfvars files are git-ignored; commit only non-secret examples).
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
