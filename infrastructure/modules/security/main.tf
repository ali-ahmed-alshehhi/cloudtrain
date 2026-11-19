# Security groups: only the load balancer is reachable from the internet.
# Owners: Hamda + Fatma.
# Attached to ALB / ECS / EC2 / RDS when those modules are wired (CKV2_AWS_5).

# checkov:skip=CKV2_AWS_5: Attached when application-services / training-compute land
# checkov:skip=CKV_AWS_382: ALB and services need egress to AWS APIs and health checks
resource "aws_security_group" "alb" {
  # checkov:skip=CKV2_AWS_5: Attached to the ALB in application-services
  # checkov:skip=CKV_AWS_382: Egress required for target health checks and AWS APIs
  name        = "${var.environment}-cloudtrain-alb"
  description = "Public load balancer for gateway and portal"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from the internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "To targets and AWS APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-cloudtrain-alb"
  }
}

resource "aws_security_group" "services" {
  # checkov:skip=CKV2_AWS_5: Attached to ECS tasks in application-services
  # checkov:skip=CKV_AWS_382: Egress required for S3/SQS/RDS and image pulls
  name        = "${var.environment}-cloudtrain-services"
  description = "Stateless ECS services inside the VPC"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Gateway, from the load balancer"
    from_port       = 5810
    to_port         = 5810
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Portal, from the load balancer"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description = "Service-to-service inside this group"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "To AWS APIs, S3, SQS and peers"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-cloudtrain-services"
  }
}

resource "aws_security_group" "workers" {
  # checkov:skip=CKV2_AWS_5: Attached to training EC2/Batch in training-compute
  # checkov:skip=CKV_AWS_382: Workers need egress for datasets, MLflow and model upload
  name        = "${var.environment}-cloudtrain-workers"
  description = "Training workers (CPU/GPU EC2)"
  vpc_id      = var.vpc_id

  ingress {
    description     = "From services (scheduler / job control)"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  egress {
    description = "To S3, SQS, MLflow and package registries"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-cloudtrain-workers"
  }
}

resource "aws_security_group" "database" {
  # checkov:skip=CKV2_AWS_5: Attached to RDS in database module
  # checkov:skip=CKV_AWS_382: Minimal egress kept for RDS managed networking
  name        = "${var.environment}-cloudtrain-database"
  description = "RDS PostgreSQL — only from services and workers"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from services"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  ingress {
    description     = "Postgres from workers"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.workers.id]
  }

  egress {
    description = "RDS managed egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-cloudtrain-database"
  }
}
