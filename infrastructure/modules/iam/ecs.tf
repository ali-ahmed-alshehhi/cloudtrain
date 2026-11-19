# IAM for running and deploying the services on ECS (least privilege).
# Drafted by Salem (Student 9) for #36 / #54; owners of the folder: Hamda + Fatma.
# Created only when enable_ecs_roles = true. Rules: security/DEPLOYMENT_POLICY.md
#
#   1. ecs_task_execution — what ECS itself uses to START a task: pull the image, write the logs,
#      read the secrets the task definition injects. It is NOT the role the service code runs as.
#   2. github_deploy      — what the GitHub Actions deploy workflow uses, through GitHub OIDC
#      (no AWS keys stored in GitHub): push images, register task definitions, update services.
#      It cannot create or delete infrastructure; that stays Terraform's job.
#
# Per-service task roles (what each service's code may touch) come with #36.

data "aws_caller_identity" "current" {
  count = var.enable_ecs_roles ? 1 : 0
}

locals {
  account_id = var.enable_ecs_roles ? data.aws_caller_identity.current[0].account_id : ""
  # Log groups /cloudtrain/<environment>/<service> (to be created with the services in #36)
  log_groups_arn = "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/cloudtrain/${var.environment}/*"
  services_arn   = "arn:aws:ecs:${var.aws_region}:${local.account_id}:service/${var.ecs_cluster_name}/*"
}

# ---------- 1. Task execution role ----------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  count = var.enable_ecs_roles ? 1 : 0

  name               = "${var.environment}-cloudtrain-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "ecs_task_execution" {
  # GetAuthorizationToken has no resource-level permissions in AWS: it only gives a login token.
  # Which images can be pulled is limited by the next statement.
  #checkov:skip=CKV_AWS_356:ecr:GetAuthorizationToken only accepts "*"
  #checkov:skip=CKV_AWS_111:ecr:GetAuthorizationToken only accepts "*"
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(var.ecr_repository_arns) > 0 ? [1] : []
    content {
      sid       = "PullOurImagesOnly"
      actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
      resources = var.ecr_repository_arns
    }
  }

  statement {
    sid       = "WriteOurLogsOnly"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.log_groups_arn}:*"]
  }

  dynamic "statement" {
    for_each = length(var.secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadInjectedSecretsOnly"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns
    }
  }
}

resource "aws_iam_role_policy" "ecs_task_execution" {
  count = var.enable_ecs_roles ? 1 : 0

  name   = "ecs-task-execution"
  role   = aws_iam_role.ecs_task_execution[0].id
  policy = data.aws_iam_policy_document.ecs_task_execution.json
}

# ---------- 2. GitHub Actions deploy role (OIDC) ----------

resource "aws_iam_openid_connect_provider" "github" {
  count = var.enable_ecs_roles ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS no longer checks this for GitHub, but the API still asks for one.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_deploy_assume" {
  count = var.enable_ecs_roles ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only our repository, and only main or the staging / production environments (with approval).
    # Pull requests and other branches cannot get this role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:environment:staging",
        "repo:${var.github_repository}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  count = var.enable_ecs_roles ? 1 : 0

  name                 = "${var.environment}-cloudtrain-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_deploy_assume[0].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_deploy" {
  #checkov:skip=CKV_AWS_356:ecr:GetAuthorizationToken and ecs Register/DescribeTaskDefinition only accept "*"
  #checkov:skip=CKV_AWS_111:ecr:GetAuthorizationToken and ecs Register/DescribeTaskDefinition only accept "*"
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(var.ecr_repository_arns) > 0 ? [1] : []
    content {
      sid = "PushOurImagesOnly"
      actions = [
        "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
      ]
      resources = var.ecr_repository_arns
    }
  }

  statement {
    sid       = "TaskDefinitions"
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    resources = ["*"]
  }

  statement {
    sid       = "UpdateOurServicesOnly"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [local.services_arn]
  }

  # A task definition names its roles; the deploy role may hand over only these, and only to ECS.
  statement {
    sid       = "PassOnlyOurTaskRoles"
    actions   = ["iam:PassRole"]
    resources = concat(aws_iam_role.ecs_task_execution[*].arn, var.task_role_arns)
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  count = var.enable_ecs_roles ? 1 : 0

  name   = "github-deploy"
  role   = aws_iam_role.github_deploy[0].id
  policy = data.aws_iam_policy_document.github_deploy.json
}
