output "task_role_arns" {
  description = "Per service: the role its code runs as (ECS task definition taskRoleArn)."
  value       = { for s, r in aws_iam_role.task : s => r.arn }
}

output "database_secret_names" {
  description = "Per service: the database secret bootstrap-schemas.sh creates (null = no database). The shared execution role (#129) should read exactly these."
  value       = { for s, schema in local.services : s => schema == null ? null : "cloudtrain/${var.environment}/database/${schema}" }
}
