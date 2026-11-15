# Security groups: only the load balancer is reachable from the internet.
# Owners: Hamda + Fatma.

resource "aws_security_group" "alb" {
  name        = "${var.environment}-cloudtrain-alb"
  description = "Public load balancer for gateway and portal"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
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
  name        = "${var.environment}-cloudtrain-services"
  description = "Stateless ECS services inside the VPC"
  vpc_id      = var.vpc_id

  ingress {
    description     = "From the load balancer"
    from_port       = 0
    to_port         = 65535
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
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment}-cloudtrain-database"
  }
}
