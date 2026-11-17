output "db_instance_id" {
  value = aws_db_instance.main.id
}

output "db_endpoint" {
  description = "Hostname:port for application DATABASE_URLs."
  value       = aws_db_instance.main.endpoint
}

output "db_address" {
  value = aws_db_instance.main.address
}

output "db_port" {
  value = aws_db_instance.main.port
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "master_secret_arn" {
  description = "RDS-managed Secrets Manager ARN for the master user (password never in Terraform state)."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}
