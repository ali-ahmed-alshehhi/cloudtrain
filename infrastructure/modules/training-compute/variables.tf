variable "environment" {
  type = string
}

variable "pool_name" {
  description = "Name of this worker pool, for example gpu-1 (one GPU per machine) or cpu."
  type        = string
}

variable "instance_type" {
  description = "Machine type. Must exist in contracts/pricing.yaml, for example g4dn.xlarge (1 GPU)."
  type        = string
}

variable "ami_id" {
  description = <<-EOT
    Machine image with the NVIDIA driver, Docker and the NVIDIA container toolkit (on real AWS:
    the AWS Deep Learning Base GPU AMI for the region). The emulator accepts any ami-... value.
  EOT
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets the workers run in."
  type        = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "instance_profile_name" {
  description = "From the iam module."
  type        = string
}

variable "desired_capacity" {
  description = "How many workers run. 0 = none: GPU machines only run while there is work (demo 4)."
  type        = number
  default     = 0
}

variable "min_size" {
  type    = number
  default = 0
}

variable "max_size" {
  description = "Upper limit, so a mistake cannot start an unlimited number of GPU machines."
  type        = number
  default     = 2
}

variable "root_volume_gb" {
  type    = number
  default = 100
}

variable "worker_env" {
  description = "Addresses the worker needs (queue URLs, bucket names), written to /etc/cloudtrain-worker.env."
  type        = map(string)
  default     = {}
}
