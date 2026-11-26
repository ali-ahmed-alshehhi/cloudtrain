# One task role per service, least privilege (security/DEPLOYMENT_POLICY.md, with Salem).
# Owners: Hamda + Fatma.
#
# The task role is what the service's CODE runs as: only the buckets and queues it calls.
# Services that call no AWS API get a task role with no permissions at all.
#
# Not here: the ECS execution role (pull the image, write logs, inject the database secret).
# That is one shared role in modules/iam/ecs.tf (Salem, #129). Each service's database secret
# is cloudtrain/<env>/database/<schema>, created by scripts/bootstrap-schemas.sh after the apply,
# so no password is in Terraform state (see the database_secret_names output).
# The access below was checked against each service's code on main (19 Nov 2026).

locals {
  prefix = "${var.environment}-cloudtrain"

  # service => database schema whose secret it reads (null = no database)
  services = {
    "gateway"            = null
    "portal"             = null
    "project-service"    = "projects"
    "dataset-service"    = "datasets"
    "job-service"        = "jobs"
    "scheduler"          = "scheduler"
    "model-registry"     = "registry"
    "inference-service"  = null
    "mlflow"             = "mlflow"
    "job-events-monitor" = null
  }

}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------- Task roles (used by the service's code) ----------

resource "aws_iam_role" "task" {
  for_each           = local.services
  name               = "${local.prefix}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

locals {
  # Only the services whose code calls S3 or SQS. Everything else gets no policy.
  task_statements = {
    # Uploads and downloads dataset files, and signs download links for workers.
    "dataset-service" = [
      { sid = "Datasets", actions = ["s3:GetObject", "s3:PutObject"], resources = ["${var.datasets_bucket_arn}/*"] },
      { sid = "ListDatasets", actions = ["s3:ListBucket"], resources = [var.datasets_bucket_arn] },
    ]
    # Sends jobs and job events; reads the dead-letter queue and queues jobs again.
    "job-service" = [
      { sid = "SendJobsAndEvents", actions = ["sqs:SendMessage", "sqs:GetQueueUrl"], resources = [var.training_jobs_queue_arn, var.job_events_queue_arn] },
      { sid = "ReadDeadLetters", actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueUrl"], resources = [var.training_jobs_dlq_arn] },
    ]
    # The only reader of training-jobs (decision 0002).
    "scheduler" = [
      { sid = "ReadJobs", actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueUrl"], resources = [var.training_jobs_queue_arn] },
    ]
    # Downloads a registered model's files.
    "inference-service" = [
      { sid = "ReadModels", actions = ["s3:GetObject"], resources = ["${var.artifacts_bucket_arn}/*"] },
      { sid = "ListModels", actions = ["s3:ListBucket"], resources = [var.artifacts_bucket_arn] },
    ]
    # The only reader of job-events (decision 0014). Same as monitoring/aws/job-events-monitor-policy.json.tftpl.
    "job-events-monitor" = [
      { sid = "ReadAndDeleteJobEventsOnly", actions = ["sqs:GetQueueUrl", "sqs:ReceiveMessage", "sqs:DeleteMessage"], resources = [var.job_events_queue_arn] },
    ]
    # MLflow's server keeps run artifacts under s3://<artifacts>/mlflow/.
    "mlflow" = [
      { sid = "MlflowArtifacts", actions = ["s3:GetObject", "s3:PutObject"], resources = ["${var.artifacts_bucket_arn}/mlflow/*"] },
      { sid = "ListMlflowArtifacts", actions = ["s3:ListBucket"], resources = [var.artifacts_bucket_arn] },
    ]
  }
}

data "aws_iam_policy_document" "task" {
  for_each = local.task_statements

  dynamic "statement" {
    for_each = each.value
    content {
      sid       = statement.value.sid
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role_policy" "task" {
  for_each = local.task_statements
  name     = "task"
  role     = aws_iam_role.task[each.key].id
  policy   = data.aws_iam_policy_document.task[each.key].json
}
