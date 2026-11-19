output "launch_template_id" {
  value = aws_launch_template.worker.id
}

output "autoscaling_group_name" {
  value = aws_autoscaling_group.worker.name
}

output "instance_type" {
  value = var.instance_type
}
