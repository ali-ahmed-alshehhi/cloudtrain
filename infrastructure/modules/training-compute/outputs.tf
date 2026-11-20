output "launch_template_id" {
  value = aws_launch_template.worker.id
}

output "autoscaling_group_name" {
  value = aws_autoscaling_group.worker.name
}

output "instance_type" {
  value = var.instance_type
}

output "worker_url" {
  description = "The pool's address for the Scheduler, or null without a load balancer."
  value       = var.enable_load_balancer ? "http://${aws_lb.worker[0].dns_name}:${var.worker_port}" : null
}
