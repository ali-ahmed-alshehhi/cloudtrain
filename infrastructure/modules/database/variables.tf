variable "environment" {
  type = string
}

variable "project" {
  type    = string
  default = "cloudtrain"
}

variable "private_subnet_ids" {
  description = "Private subnets for the RDS subnet group (no public access)."
  type        = list(string)
}

variable "database_security_group_id" {
  description = "Security group that allows Postgres only from services and workers."
  type        = string
}

variable "db_name" {
  description = "Initial database name (one DB, many schemas)."
  type        = string
  default     = "cloudtrain"
}

variable "db_username" {
  description = "Master username (schemas get their own roles via bootstrap SQL)."
  type        = string
  default     = "cloudtrain_admin"
}

variable "instance_class" {
  description = "RDS instance size. Keep small in dev."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "engine_version" {
  type    = string
  default = "17"
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  description = "Keep false for disposable dev; true for staging."
  type        = bool
  default     = false
}
