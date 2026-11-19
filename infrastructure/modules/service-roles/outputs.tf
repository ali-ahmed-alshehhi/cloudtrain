output "task_role_arns" {
  description = "Per service: the role its code runs as (ECS task definition taskRoleArn)."
  value       = { for s, r in aws_iam_role.task : s => r.arn }
}

output "execution_role_arns" {
  description = "Per service: the role ECS uses to start it (executionRoleArn)."
  value       = { for s, r in aws_iam_role.execution : s => r.arn }
}

output "log_groups" {
  description = "Per service: the CloudWatch log group name its execution role may write to."
  value       = local.log_group
}

output "database_secret_names" {
  description = "Per service: the Secrets Manager secret bootstrap-schemas.sh creates (null = no database)."
  value       = { for s, schema in local.services : s => schema == null ? null : "cloudtrain/${var.environment}/database/${schema}" }
}
