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
