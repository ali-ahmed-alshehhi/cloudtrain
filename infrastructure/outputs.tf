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

output "db_address" {
  description = "RDS hostname (for bootstrap / DATABASE_URLs)."
  value       = try(module.database[0].db_address, null)
}

output "db_port" {
  description = "RDS port (for bootstrap / DATABASE_URLs)."
  value       = try(module.database[0].db_port, null)
}

output "db_name" {
  description = "Postgres database name."
  value       = try(module.database[0].db_name, null)
}

output "db_master_secret_arn" {
  description = "RDS-managed Secrets Manager ARN for the master user (Fatma/Hamda + services)."
  value       = try(module.database[0].master_secret_arn, null)
}

output "jwt_issuer" {
  description = "JWT_ISSUER for the gateway (from Cognito / emulator)."
  value       = try(module.identity[0].issuer, null)
}

output "jwt_audience" {
  description = "JWT_AUDIENCE for the gateway (portal Cognito app client id)."
  value       = try(module.identity[0].portal_client_id, null)
}

output "jwt_jwks_url" {
  description = "JWT_JWKS_URL for the gateway (Cognito public keys)."
  value       = try(module.identity[0].jwks_url, null)
}

output "cognito_user_pool_id" {
  value = try(module.identity[0].user_pool_id, null)
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

output "service_task_role_arns" {
  description = "Per service: the IAM role its code runs as (ECS taskRoleArn; Salem: PassRole in #129)."
  value       = try(module.service_roles[0].task_role_arns, null)
}

output "service_database_secret_names" {
  description = "Per service: the database secret created by scripts/bootstrap-schemas.sh."
  value       = try(module.service_roles[0].database_secret_names, null)
}

output "ecs_task_execution_role_arn" {
  description = "executionRoleArn for every ECS task definition (Hamda + Fatma, #36)."
  value       = try(module.iam[0].ecs_task_execution_role_arn, null)
}

output "github_deploy_role_arn" {
  description = "Repository variable AWS_DEPLOY_ROLE_ARN for the deploy workflow (Salem, #54)."
  value       = try(module.iam[0].github_deploy_role_arn, null)
}

output "ecs_cluster_name" {
  description = "ECS cluster for Salem's deploy (#54). Always <environment>-cloudtrain."
  value       = try(module.application_services[0].ecs_cluster_name, null)
}

output "ecs_service_names" {
  description = "Per service: ECS service name in the cluster."
  value       = try(module.application_services[0].ecs_service_names, null)
}

output "alb_dns_name" {
  description = "Public load balancer DNS (gateway and portal)."
  value       = try(module.application_services[0].alb_dns_name, null)
}

output "gateway_url" {
  value = try(module.application_services[0].gateway_url, null)
}

output "portal_url" {
  value = try(module.application_services[0].portal_url, null)
}
