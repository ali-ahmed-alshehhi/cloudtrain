variable "environment" {
  description = "dev or staging."
  type        = string
}

variable "aws_region" {
  description = "Region of the user pool (used to build the issuer address on AWS)."
  type        = string
}

variable "issuer_base_url" {
  description = "Empty on AWS. On the AWS Emulator: its address, e.g. https://127.0.0.1:9297."
  type        = string
  default     = ""
}

variable "allow_admin_password_login" {
  description = "Let the test script log in with a password from the command line. Emulator and dev only."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Refuse to delete the user pool. On for anything with real users."
  type        = bool
  default     = false
}

variable "roles" {
  description = "Role groups. The gateway and services read them from the token's cognito:groups claim."
  type        = map(string)
  default = {
    "admin"          = "Manages projects, members and models"
    "data-scientist" = "Uploads data and submits training jobs"
    "viewer"         = "Reads projects, jobs and results only"
  }
}
