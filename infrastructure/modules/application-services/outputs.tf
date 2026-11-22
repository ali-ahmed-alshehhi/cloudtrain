output "ecs_cluster_name" {
  description = "Must stay <environment>-cloudtrain for Salem's deploy role (#129)."
  value       = aws_ecs_cluster.this.name
}

output "ecs_cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "ecs_service_names" {
  description = "Service names in the cluster (Salem #54)."
  value       = { for name, svc in aws_ecs_service.service : name => svc.name }
}

output "alb_dns_name" {
  description = "Public load balancer DNS (gateway :5810, portal :3000)."
  value       = aws_lb.public.dns_name
}

output "alb_arn" {
  value = aws_lb.public.arn
}

output "alb_arn_suffix" {
  description = "For monitoring's ALB 5xx alarm (AWS/ApplicationELB dimensions)."
  value       = aws_lb.public.arn_suffix
}

output "gateway_url" {
  value = "http://${aws_lb.public.dns_name}:5810"
}

output "portal_url" {
  value = "http://${aws_lb.public.dns_name}:3000"
}

output "log_group_names" {
  description = "Log groups used by the task definitions (created here or passed from monitoring)."
  value       = local.log_group_names
}

output "task_definition_arns" {
  value = { for name, td in aws_ecs_task_definition.service : name => td.arn }
}
