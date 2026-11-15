output "training_jobs_queue_url" {
  value = aws_sqs_queue.training_jobs.url
}

output "training_jobs_queue_arn" {
  value = aws_sqs_queue.training_jobs.arn
}

output "training_jobs_dlq_url" {
  value = aws_sqs_queue.training_jobs_dlq.url
}

output "job_events_queue_url" {
  value = aws_sqs_queue.job_events.url
}

output "job_events_queue_arn" {
  value = aws_sqs_queue.job_events.arn
}
