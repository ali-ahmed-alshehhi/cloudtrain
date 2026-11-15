output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "services_security_group_id" {
  value = aws_security_group.services.id
}

output "workers_security_group_id" {
  value = aws_security_group.workers.id
}

output "database_security_group_id" {
  value = aws_security_group.database.id
}
