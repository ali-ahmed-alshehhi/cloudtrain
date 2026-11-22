# CloudWatch logs and alarms (#36). Owners: Hamda + Fatma.
# The alarms follow monitoring/aws/README.md from Hilal + Adel (#109, #115): same metrics and
# thresholds as the local Prometheus rules. On the AWS Emulator (decision 0011) they are created to
# show the setup, but receive no live data; the live dashboard is the local Grafana.

locals {
  # SQS names from their ARNs (arn:aws:sqs:<region>:<account>:<name>)
  training_jobs_dlq_name = element(split(":", var.training_jobs_dlq_arn), 5)
  job_events_queue_name  = element(split(":", var.job_events_queue_arn), 5)
}

# ---------- Log groups: one per ECS service ----------

resource "aws_cloudwatch_log_group" "service" {
  # checkov:skip=CKV_AWS_158: CloudWatch encrypts logs by default; a customer KMS key is not needed for dev logs
  # checkov:skip=CKV_AWS_338: Dev logs are for debugging; 14 days is enough and keeps cost down (log_retention_days)
  for_each          = toset(var.services)
  name              = "/cloudtrain/${var.environment}/${each.key}"
  retention_in_days = var.log_retention_days

  tags = {
    Service = each.key
  }
}

# ---------- Alarms ----------

# A job failed 3 times and landed on the dead-letter queue (local twin: CloudTrainDeadLetters).
resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  alarm_name          = "${var.environment}-cloudtrain-dead-letters"
  alarm_description   = "A training job failed 3 times and is on ${local.training_jobs_dlq_name}. Mariam's dead-letter reader retries it; look at why it failed."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = local.training_jobs_dlq_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}

# Nobody is reading job events: the oldest one waits more than 5 minutes (local twin: CloudTrainJobEventsNotRead).
resource "aws_cloudwatch_metric_alarm" "job_events_not_read" {
  alarm_name          = "${var.environment}-cloudtrain-job-events-not-read"
  alarm_description   = "The oldest message on ${local.job_events_queue_name} is older than 5 minutes: job-events-monitor is not reading."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = local.job_events_queue_name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 300
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}

# More than 5% of requests through the public load balancer fail with 5xx for 5 minutes
# (local twin: CloudTrainHighErrorRate). Created once application-services gives us the ALB.
resource "aws_cloudwatch_metric_alarm" "server_errors" {
  count               = var.alb_arn_suffix == null ? 0 : 1
  alarm_name          = "${var.environment}-cloudtrain-server-errors"
  alarm_description   = "More than 5% of requests to the gateway or portal answer 5xx."
  evaluation_periods  = 5
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  # IF/FILL are CloudWatch's documented metric-math functions (Adil, #134): no division by zero,
  # and a minute with no 5xx (no data point) counts as 0.
  metric_query {
    id          = "error_rate"
    expression  = "IF(requests > 0, 100 * (FILL(target_errors, 0) + FILL(elb_errors, 0)) / requests, 0)"
    label       = "5xx percent"
    return_data = true
  }

  # 5xx answered by the services behind the load balancer.
  metric_query {
    id = "target_errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      stat        = "Sum"
      period      = 60
    }
  }

  # 5xx the load balancer answers itself, for example when no gateway task is healthy.
  metric_query {
    id = "elb_errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_ELB_5XX_Count"
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      stat        = "Sum"
      period      = 60
    }
  }

  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      stat        = "Sum"
      period      = 60
    }
  }
}
