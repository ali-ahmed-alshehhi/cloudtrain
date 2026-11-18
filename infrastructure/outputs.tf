# Values other people need after `terraform apply`.
# Owners: Hamda + Fatma. Never output a secret.

output "datasets_bucket" {
  description = "S3 bucket for Faisal (dataset-service)."
  value       = module.object_storage.datasets_bucket_name
}

output "artifacts_bucket" {
  description = "S3 bucket for Abdullah / Majed (checkpoints, models)."
  value       = module.object_storage.artifacts_bucket_name
}

output "training_jobs_queue_url" {
  description = "SQS queue Mariam writes; Maitha is the only reader."
  value       = module.message_queue.training_jobs_queue_url
}

output "training_jobs_dlq_url" {
  value = module.message_queue.training_jobs_dlq_url
}

output "job_events_queue_url" {
  value = module.message_queue.job_events_queue_url
}

output "vpc_id" {
  value = try(module.networking[0].vpc_id, null)
}

output "public_subnet_ids" {
  value = try(module.networking[0].public_subnet_ids, [])
}

output "private_subnet_ids" {
  value = try(module.networking[0].private_subnet_ids, [])
}

output "ecr_repository_urls" {
  description = "Image repos Salem pushes to."
  value       = try(module.container_registry[0].repository_urls, {})
}

output "alb_security_group_id" {
  value = try(module.security[0].alb_security_group_id, null)
}

output "services_security_group_id" {
  value = try(module.security[0].services_security_group_id, null)
}

output "database_security_group_id" {
  value = try(module.security[0].database_security_group_id, null)
}

output "db_endpoint" {
  description = "RDS endpoint for service DATABASE_URLs (after enable_database=true)."
  value       = try(module.database[0].db_endpoint, null)
}

output "db_master_secret_arn" {
  description = "Secrets Manager ARN for the RDS master user (Fatma/Hamda + services)."
  value       = try(module.database[0].master_secret_arn, null)
}

output "gpu_worker_autoscaling_group" {
  description = "Auto Scaling group of GPU workers (Abdullah, Maitha)."
  value       = try(module.training_compute_gpu[0].autoscaling_group_name, null)
}

output "gpu_worker_launch_template_id" {
  value = try(module.training_compute_gpu[0].launch_template_id, null)
}

output "worker_instance_profile_name" {
  value = try(module.iam[0].worker_instance_profile_name, null)
}
