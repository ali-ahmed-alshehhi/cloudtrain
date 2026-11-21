# SQS: training-jobs (+ DLQ redrive) and job-events, encrypted.
# Owners: Hamda + Fatma.

resource "aws_sqs_queue" "training_jobs_dlq" {
  name                    = var.training_jobs_dlq_name
  sqs_managed_sse_enabled = true
  # 14 days (SQS max) so Mariam's "failed for good" reports survive a weekend
  message_retention_seconds = 1209600

  tags = {
    Name    = var.training_jobs_dlq_name
    Purpose = "training-jobs-dlq"
  }
}

resource "aws_sqs_queue" "training_jobs" {
  name                       = var.training_jobs_queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.training_jobs_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = {
    Name    = var.training_jobs_queue_name
    Purpose = "training-jobs"
  }
}

resource "aws_sqs_queue" "job_events" {
  name                    = var.job_events_queue_name
  sqs_managed_sse_enabled = true

  tags = {
    Name    = var.job_events_queue_name
    Purpose = "job-events"
  }
}
