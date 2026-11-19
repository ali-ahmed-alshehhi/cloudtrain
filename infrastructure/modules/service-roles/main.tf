# One IAM role per service, least privilege (security/DEPLOYMENT_POLICY.md, with Salem).
# Owners: Hamda + Fatma.
#
# Each service gets two roles:
# - an execution role, used by ECS itself: pull the service's own image, write its own logs,
#   and read ONLY its own database secret (injected into the container as DATABASE_URL);
# - a task role, used by the service's code: only the buckets and queues it calls.
#   Services that call no AWS API get a task role with no permissions at all.
#
# The database secrets are NOT created here: infrastructure/scripts/bootstrap-schemas.sh creates
# cloudtrain/<env>/database/<schema> after `terraform apply`, so no password is in Terraform state.
# The access below was checked against each service's code on main (19 Nov 2026).

data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  prefix  = "${var.environment}-cloudtrain"

  # service => database schema whose secret it reads (null = no database)
  services = {
    "gateway"           = null
    "portal"            = null
    "project-service"   = "projects"
    "dataset-service"   = "datasets"
    "job-service"       = "jobs"
    "scheduler"         = "scheduler"
    "model-registry"    = "registry"
    "inference-service" = null
    "mlflow"            = "mlflow"
  }

  log_group = { for s, _ in local.services : s => "/ecs/${local.prefix}/${s}" }
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

# ---------- Execution roles (used by ECS to start the container) ----------

resource "aws_iam_role" "execution" {
  for_each           = local.services
  name               = "${local.prefix}-${each.key}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "execution" {
  for_each = local.services

  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"] # AWS only allows "*" for this action
    resources = ["*"]
  }

  statement {
    sid       = "PullOwnImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = ["arn:aws:ecr:${var.aws_region}:${local.account}:repository/cloudtrain/${var.environment}/${each.key}"]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${local.account}:log-group:${local.log_group[each.key]}:*"]
  }

  dynamic "statement" {
    for_each = each.value == null ? [] : [each.value]
    content {
      sid       = "ReadOwnDatabaseSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = ["arn:aws:secretsmanager:${var.aws_region}:${local.account}:secret:cloudtrain/${var.environment}/database/${statement.value}-*"]
    }
  }
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.services
  name     = "execution"
  role     = aws_iam_role.execution[each.key].id
  policy   = data.aws_iam_policy_document.execution[each.key].json
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
