# Training workers: EC2 machines in an Auto Scaling group (decision 0012).
# Owners: Hamda + Fatma.
#
# The number of machines is one variable (desired_capacity). Change it and run `terraform apply`:
# the group adds or removes machines, nothing is rebuilt by hand (demo step 4).

locals {
  name = "${var.environment}-cloudtrain-${var.pool_name}"

  env_file = join("\n", [for k, v in var.worker_env : "${k}=${v}"])
}

resource "aws_launch_template" "worker" {
  name_prefix   = "${local.name}-"
  image_id      = var.ami_id
  instance_type = var.instance_type

  iam_instance_profile {
    name = var.instance_profile_name
  }

  vpc_security_group_ids = var.security_group_ids

  # IMDSv2 only: a process in a container cannot read the machine's credentials with a plain GET.
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  monitoring {
    enabled = true
  }

  ebs_optimized = true

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = var.root_volume_gb
      volume_type = "gp3"
      encrypted   = true
    }
  }

  user_data = base64encode(<<-EOT
    #!/bin/bash
    # The worker image reads its addresses from here. No secrets: the machine's IAM role
    # gives it access to S3 and the job-events queue.
    cat > /etc/cloudtrain-worker.env <<'ENV'
    ${local.env_file}
    ENV
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name    = local.name
      Purpose = "training-worker"
    }
  }
}

resource "aws_autoscaling_group" "worker" {
  name                = local.name
  min_size            = var.min_size
  max_size            = var.max_size
  desired_capacity    = var.desired_capacity
  vpc_zone_identifier = var.subnet_ids
  # New machines join the load balancer by themselves; removed ones leave it.
  target_group_arns = aws_lb_target_group.worker[*].arn

  launch_template {
    id      = aws_launch_template.worker.id
    version = aws_launch_template.worker.latest_version
  }

  tag {
    key                 = "Name"
    value               = local.name
    propagate_at_launch = true
  }
}

# ---------- Internal load balancer: one address per pool for the Scheduler ----------
# The Scheduler posts a job to http://<this address>:8010. A busy worker answers 409 and the
# Scheduler retries, which then reaches another machine of the same pool.

resource "aws_lb" "worker" {
  # checkov:skip=CKV_AWS_91: Access logs not needed for an internal, lab-only worker endpoint
  # checkov:skip=CKV_AWS_150: Disposable dev load balancer; terraform destroy must be able to remove it
  count              = var.enable_load_balancer ? 1 : 0
  name               = local.name
  internal           = true
  load_balancer_type = "network"
  subnets            = var.subnet_ids

  enable_cross_zone_load_balancing = true

  tags = {
    Name    = local.name
    Purpose = "training-worker-endpoint"
  }
}

resource "aws_lb_target_group" "worker" {
  count       = var.enable_load_balancer ? 1 : 0
  name        = local.name
  port        = var.worker_port
  protocol    = "TCP"
  vpc_id      = var.vpc_id
  target_type = "instance"

  health_check {
    protocol = "HTTP"
    path     = "/health"
    port     = "traffic-port"
  }
}

resource "aws_lb_listener" "worker" {
  count             = var.enable_load_balancer ? 1 : 0
  load_balancer_arn = aws_lb.worker[0].arn
  port              = var.worker_port
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.worker[0].arn
  }
}
