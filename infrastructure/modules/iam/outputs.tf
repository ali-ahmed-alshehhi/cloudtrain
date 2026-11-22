output "worker_instance_profile_name" {
  value = aws_iam_instance_profile.worker.name
}

output "worker_role_arn" {
  value = aws_iam_role.worker.arn
}

output "ecs_task_execution_role_arn" {
  value = try(aws_iam_role.ecs_task_execution[0].arn, null)
}

output "github_deploy_role_arn" {
  description = "Set as the repository variable AWS_DEPLOY_ROLE_ARN to deploy from GitHub Actions."
  value       = try(aws_iam_role.github_deploy[0].arn, null)
}
