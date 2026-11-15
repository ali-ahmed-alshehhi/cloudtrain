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
