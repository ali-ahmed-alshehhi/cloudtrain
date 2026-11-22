# ECS Fargate services + public ALB for gateway and portal (#36).
# Owners: Hamda + Fatma.
#
# Cluster name is <environment>-cloudtrain (Salem's deploy role in #129).
# Log groups: prefer monitoring's log_group_names; otherwise create /cloudtrain/<env>/<service>.
# Worker LBs stay in Fatma's training-compute work — this ALB is public only.

data "aws_caller_identity" "current" {}

locals {
  cluster_name = "${var.environment}-cloudtrain"
  account_id   = data.aws_caller_identity.current.account_id

  # Ports from contracts/ports.md. training-worker stays on EC2 (decision 0012), not Fargate.
  services = {
    gateway           = { port = 5810, cpu = "512", memory = "1024", public = true }
    portal            = { port = 3000, cpu = "256", memory = "512", public = true }
    project-service   = { port = 8001, cpu = "256", memory = "512", public = false }
    dataset-service   = { port = 8002, cpu = "256", memory = "512", public = false }
    job-service       = { port = 8003, cpu = "256", memory = "512", public = false }
    scheduler         = { port = 8004, cpu = "256", memory = "512", public = false }
    model-registry    = { port = 8006, cpu = "256", memory = "512", public = false }
    inference-service = { port = 8007, cpu = "512", memory = "1024", public = false }
    mlflow            = { port = 5000, cpu = "256", memory = "512", public = false }
  }

  alb_sg_id      = var.alb_security_group_id != "" ? var.alb_security_group_id : var.default_security_group_id
  services_sg_id = var.services_security_group_id != "" ? var.services_security_group_id : var.default_security_group_id

  # Log group names: monitoring output, or create them here.
  create_log_groups = length(var.log_group_names) == 0
  log_group_names = local.create_log_groups ? {
    for name in keys(local.services) : name => "/cloudtrain/${var.environment}/${name}"
  } : var.log_group_names

  dns_suffix = var.enable_service_discovery ? aws_service_discovery_private_dns_namespace.this[0].name : "cloudtrain.local"

  service_base_urls = {
    for name, cfg in local.services : name => "http://${name}.${local.dns_suffix}:${cfg.port}"
  }
}

# ---------- Cluster ----------

resource "aws_ecs_cluster" "this" {
  name = local.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = local.cluster_name
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# ---------- Log groups (until monitoring module owns them) ----------

resource "aws_cloudwatch_log_group" "service" {
  # checkov:skip=CKV_AWS_158: Lab log groups use CloudWatch default encryption
  for_each = local.create_log_groups ? local.services : {}

  name              = "/cloudtrain/${var.environment}/${each.key}"
  retention_in_days = 365

  tags = {
    Name = each.key
  }
}

# ---------- Service discovery (internal URLs) ----------

resource "aws_service_discovery_private_dns_namespace" "this" {
  count = var.enable_service_discovery ? 1 : 0

  name        = "${var.environment}.cloudtrain.local"
  description = "CloudTrain ${var.environment} service-to-service DNS"
  vpc         = var.vpc_id
}

resource "aws_service_discovery_service" "this" {
  for_each = var.enable_service_discovery ? local.services : {}

  name = each.key

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this[0].id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ---------- Public ALB (gateway + portal only) ----------

resource "aws_lb" "public" {
  # checkov:skip=CKV_AWS_91: Access logs deferred to monitoring
  # checkov:skip=CKV2_AWS_28: WAF out of lab scope
  # checkov:skip=CKV_AWS_150: Dev/emulator must allow terraform destroy; enable on staging later
  # checkov:skip=CKV2_AWS_20: No ACM on emulator; HTTP only until real cert (contracts/ports.md)
  name                       = "${var.environment}-cloudtrain-alb"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [local.alb_sg_id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
  enable_deletion_protection = false

  tags = {
    Name = "${var.environment}-cloudtrain-alb"
  }
}

resource "aws_lb_target_group" "gateway" {
  # checkov:skip=CKV_AWS_378: Targets are HTTP containers (gateway :5810); TLS terminates later with ACM
  name        = "${var.environment}-ct-gateway"
  port        = 5810
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = {
    Name = "gateway"
  }
}

resource "aws_lb_target_group" "portal" {
  # checkov:skip=CKV_AWS_378: Targets are HTTP containers (portal :3000); TLS terminates later with ACM
  name        = "${var.environment}-ct-portal"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200-399"
  }

  tags = {
    Name = "portal"
  }
}

# HTTP listeners: contracts/ports.md publishes gateway :5810 and portal :3000.
# No ACM certificate on the emulator (decision 0011); HTTPS comes with a real account.
resource "aws_lb_listener" "gateway" {
  # checkov:skip=CKV_AWS_2: HTTP until ACM exists; published port 5810 per contracts/ports.md
  # checkov:skip=CKV_AWS_103: TLS policy N/A for HTTP listener on the emulator
  load_balancer_arn = aws_lb.public.arn
  port              = 5810
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}

resource "aws_lb_listener" "portal" {
  # checkov:skip=CKV_AWS_2: HTTP until ACM exists; published port 3000 per contracts/ports.md
  # checkov:skip=CKV_AWS_103: TLS policy N/A for HTTP listener on the emulator
  load_balancer_arn = aws_lb.public.arn
  port              = 3000
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.portal.arn
  }
}

# ---------- Task definitions ----------

locals {
  # Secrets Manager ARN ends with -?????? ; ECS accepts the name-based ARN form when the secret exists.
  database_secret_arns = {
    for name, secret_name in var.database_secret_names :
    name => secret_name == null ? null : "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${secret_name}"
    if secret_name != null
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each = local.services

  family                   = "${local.cluster_name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = lookup(var.task_role_arns, each.key, null)

  container_definitions = jsonencode([
    merge(
      {
        name      = each.key
        image     = "${var.ecr_repository_urls[each.key]}:${var.image_tag}"
        essential = true
        portMappings = [
          {
            containerPort = each.value.port
            hostPort      = each.value.port
            protocol      = "tcp"
          }
        ]
        environment = concat(
          [
            { name = "ENVIRONMENT", value = var.environment },
            { name = "LOG_LEVEL", value = "INFO" },
            { name = "AWS_REGION", value = var.aws_region },
            { name = "DATASETS_BUCKET", value = var.datasets_bucket },
            { name = "ARTIFACTS_BUCKET", value = var.artifacts_bucket },
            { name = "TRAINING_JOBS_QUEUE", value = "training-jobs" },
            { name = "TRAINING_JOBS_DLQ", value = "training-jobs-dlq" },
            { name = "JOB_EVENTS_QUEUE", value = "job-events" },
            { name = "TRAINING_JOBS_QUEUE_URL", value = var.training_jobs_queue_url },
            { name = "TRAINING_JOBS_DLQ_URL", value = var.training_jobs_dlq_url },
            { name = "JOB_EVENTS_QUEUE_URL", value = var.job_events_queue_url },
            { name = "PROJECT_SERVICE_URL", value = local.service_base_urls["project-service"] },
            { name = "DATASET_SERVICE_URL", value = local.service_base_urls["dataset-service"] },
            { name = "JOB_SERVICE_URL", value = local.service_base_urls["job-service"] },
            { name = "SCHEDULER_URL", value = local.service_base_urls["scheduler"] },
            { name = "MODEL_REGISTRY_URL", value = local.service_base_urls["model-registry"] },
            { name = "INFERENCE_SERVICE_URL", value = local.service_base_urls["inference-service"] },
            { name = "MLFLOW_URL", value = local.service_base_urls["mlflow"] },
            { name = "MLFLOW_TRACKING_URI", value = local.service_base_urls["mlflow"] },
            { name = "AUTH_MODE", value = var.jwt_issuer != "" ? "jwt" : "dev" },
            { name = "JWT_ISSUER", value = var.jwt_issuer },
            { name = "JWT_AUDIENCE", value = var.jwt_audience },
            { name = "JWT_JWKS_URL", value = var.jwt_jwks_url },
          ],
          var.worker_urls_json != "" ? [{ name = "TRAINING_WORKER_URLS", value = var.worker_urls_json }] : [],
          each.key == "portal" ? [{ name = "NEXT_PUBLIC_GATEWAY_URL", value = "http://${aws_lb.public.dns_name}:5810" }] : [],
        )
        secrets = lookup(local.database_secret_arns, each.key, null) != null ? [
          {
            name      = "DATABASE_URL"
            valueFrom = local.database_secret_arns[each.key]
          }
        ] : []
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = local.log_group_names[each.key]
            "awslogs-region"        = var.aws_region
            "awslogs-stream-prefix" = each.key
          }
        }
      },
      each.key == "portal" ? {} : {
        healthCheck = {
          command     = ["CMD-SHELL", "curl -f http://localhost:${each.value.port}/health || exit 1"]
          interval    = 30
          timeout     = 5
          retries     = 3
          startPeriod = 60
        }
      }
    )
  ])

  tags = {
    Name = each.key
  }
}

# ---------- ECS services ----------

resource "aws_ecs_service" "service" {
  for_each = local.services

  name            = each.key
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [local.services_sg_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.key == "gateway" ? [1] : each.key == "portal" ? [1] : []
    content {
      target_group_arn = each.key == "gateway" ? aws_lb_target_group.gateway.arn : aws_lb_target_group.portal.arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }

  dynamic "service_registries" {
    for_each = var.enable_service_discovery ? [1] : []
    content {
      registry_arn = aws_service_discovery_service.this[each.key].arn
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  # Deploy workflow registers new revisions; don't force a new deployment on every apply.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [
    aws_lb_listener.gateway,
    aws_lb_listener.portal,
    aws_cloudwatch_log_group.service,
  ]

  tags = {
    Name = each.key
  }
}
