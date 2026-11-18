# Remote-state bootstrap: creates the S3 bucket that holds CloudTrain's Terraform state.
# Owners: Hamda + Fatma (Student 6).
#
# Run this ONCE per account (the AWS Emulator, or a real AWS account) BEFORE switching the
# root module (infrastructure/) to the S3 backend. This folder keeps its own small local
# state file, which git ignores. See README.md in this folder.

terraform {
  # S3-native state locking (use_lockfile in the root backend) needs Terraform 1.10 or later.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Emulator: credentials and CA certificate come from `source ../scripts/emulator-env.sh`.
  # Real AWS: AWS_PROFILE or an IAM role.
  skip_credentials_validation = var.use_emulator
  skip_metadata_api_check     = var.use_emulator
  skip_requesting_account_id  = var.use_emulator
  # The emulator only answers path-style S3 addresses (https://127.0.0.1:9297/<bucket>).
  s3_use_path_style = var.use_emulator

  dynamic "endpoints" {
    for_each = var.use_emulator ? [1] : []
    content {
      s3  = var.emulator_endpoint
      sts = var.emulator_endpoint
      iam = var.emulator_endpoint
    }
  }

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      Owner       = var.owner
    }
  }
}

resource "aws_s3_bucket" "state" {
  # checkov:skip=CKV_AWS_144: Single-region lab; cross-region replication of state is out of scope
  # checkov:skip=CKV_AWS_145: AES256 server-side encryption meets the lab requirement; KMS with Salem later
  # checkov:skip=CKV_AWS_18: Access logging deferred to the monitoring module
  # checkov:skip=CKV2_AWS_62: Nothing needs to react to state file changes
  bucket = var.state_bucket_name

  # Emulator practice: let `terraform destroy` remove the bucket with its state inside.
  # Real AWS: destroy refuses while state files exist, so the state cannot be lost by accident.
  force_destroy = var.use_emulator

  tags = {
    Name    = var.state_bucket_name
    Purpose = "terraform-state"
  }
}

# Every change to the state is kept as a version, so a bad apply can be rolled back.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Restricted access, part 1: the state bucket can never be made public.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Restricted access, part 2: refuse any request that is not sent over TLS (HTTPS).
# Who may read the state at all is decided by IAM permissions (with Salem).
data "aws_iam_policy_document" "state" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  count = var.enforce_tls ? 1 : 0

  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state.json

  # The public access block must exist first, or S3 can refuse the policy.
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# Old state versions are kept for a while, then removed, so the bucket does not grow forever.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_days
    }
  }

  # Lifecycle rules on a versioned bucket must come after versioning is on.
  depends_on = [aws_s3_bucket_versioning.state]
}
