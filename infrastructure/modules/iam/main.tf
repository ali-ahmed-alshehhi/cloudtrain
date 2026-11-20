# IAM for the training workers (least privilege). Service roles for ECS come in #36, with Salem.
# Owners: Hamda + Fatma.
#
# A worker can: read datasets, read and write artifacts, send job events.
# It cannot touch the training-jobs queue (Maitha's scheduler is its only reader), the database
# or Secrets Manager.

data "aws_iam_policy_document" "worker_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${var.environment}-cloudtrain-worker"
  assume_role_policy = data.aws_iam_policy_document.worker_assume.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "ReadDatasets"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.datasets_bucket_arn, "${var.datasets_bucket_arn}/*"]
  }

  statement {
    sid       = "ReadWriteArtifacts"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.artifacts_bucket_arn, "${var.artifacts_bucket_arn}/*"]
  }

  statement {
    sid       = "ReportJobEvents"
    actions   = ["sqs:SendMessage"]
    resources = [var.job_events_queue_arn]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_iam_instance_profile" "worker" {
  name = "${var.environment}-cloudtrain-worker"
  role = aws_iam_role.worker.name
}
