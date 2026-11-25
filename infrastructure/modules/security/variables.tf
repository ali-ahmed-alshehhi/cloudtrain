variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  description = "The VPC's address range, for load balancer health checks to the workers."
  type        = string
}

variable "worker_port" {
  description = "The training worker's port (contracts/ports.md)."
  type        = number
  default     = 8010
}
