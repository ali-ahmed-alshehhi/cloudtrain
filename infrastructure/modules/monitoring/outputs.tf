output "log_group_names" {
  description = "Per service: its CloudWatch log group (awslogs-group in the ECS task definition)."
  value       = { for s, g in aws_cloudwatch_log_group.service : s => g.name }
}

output "alarm_names" {
  value = concat(
    [aws_cloudwatch_metric_alarm.dead_letters.alarm_name, aws_cloudwatch_metric_alarm.job_events_not_read.alarm_name],
    aws_cloudwatch_metric_alarm.server_errors[*].alarm_name,
  )
}
