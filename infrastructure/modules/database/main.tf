# RDS PostgreSQL — private, encrypted, one database with per-service schemas.
# Owners: Hamda + Fatma (Student 6).
# Schema/role bootstrap: scripts/bootstrap-schemas.sh (run once after apply).
# Master password: RDS-managed Secrets Manager (never in Terraform state).

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.environment}-cloudtrain-db"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.environment}-cloudtrain-db"
  }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${var.environment}-cloudtrain-postgres17"
  family = "postgres17"

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = {
    Name = "${var.environment}-cloudtrain-postgres17"
  }
}

resource "aws_db_instance" "main" {
  # checkov:skip=CKV_AWS_157: Single-AZ in dev for lab cost; multi_az is the db_multi_az variable (true on real AWS)
  # checkov:skip=CKV_AWS_293: Performance Insights optional for lab cost control
  # checkov:skip=CKV_AWS_353: Performance Insights KMS optional for lab
  # checkov:skip=CKV_AWS_118: Enhanced monitoring deferred for lab cost; enable with monitoring module
  # checkov:skip=CKV_AWS_354: Enhanced monitoring deferred for lab cost
  # checkov:skip=CKV2_AWS_60: Auto minor version upgrade on; major controlled by us
  identifier     = "${var.environment}-cloudtrain-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.allocated_storage_gb * 2
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.database_security_group_id]
  parameter_group_name   = aws_db_parameter_group.postgres.name
  publicly_accessible    = false
  multi_az               = var.multi_az

  iam_database_authentication_enabled = true
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]

  backup_retention_period   = var.backup_retention_days
  backup_window             = "03:00-04:00"
  maintenance_window        = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot     = true
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${var.environment}-cloudtrain-final" : null

  auto_minor_version_upgrade = true

  tags = {
    Name    = "${var.environment}-cloudtrain-postgres"
    Purpose = "shared-postgres"
  }
}
