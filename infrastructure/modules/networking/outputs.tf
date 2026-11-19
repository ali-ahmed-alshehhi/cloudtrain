output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "default_security_group_id" {
  description = "The VPC's default security group, locked down (no rules) by this module."
  value       = aws_default_security_group.default.id
}
