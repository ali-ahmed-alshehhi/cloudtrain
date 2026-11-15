# S3 buckets datasets + artifacts: encrypted, no public access.
# Owners: Hamda + Fatma.

# checkov:skip=CKV_AWS_144: Single-region lab; cross-region replication out of scope
# checkov:skip=CKV_AWS_145: AES256 SSE meets lab encryption requirement; KMS with Salem later
# checkov:skip=CKV_AWS_18: Access logging deferred to monitoring module
# checkov:skip=CKV2_AWS_62: Event notifications not required for dataset/artifact storage yet
resource "aws_s3_bucket" "datasets" {
  # checkov:skip=CKV_AWS_144: Single-region lab
  # checkov:skip=CKV_AWS_145: AES256 sufficient for lab; KMS later
  # checkov:skip=CKV_AWS_18: Access logging in monitoring module
  # checkov:skip=CKV2_AWS_62: Notifications not required yet
  bucket = var.datasets_bucket_name

  tags = {
    Name    = var.datasets_bucket_name
    Purpose = "datasets"
  }
}

resource "aws_s3_bucket" "artifacts" {
  # checkov:skip=CKV_AWS_144: Single-region lab
  # checkov:skip=CKV_AWS_145: AES256 sufficient for lab; KMS later
  # checkov:skip=CKV_AWS_18: Access logging in monitoring module
  # checkov:skip=CKV2_AWS_62: Notifications not required yet
  bucket = var.artifacts_bucket_name

  tags = {
    Name    = var.artifacts_bucket_name
    Purpose = "artifacts"
  }
}

resource "aws_s3_bucket_versioning" "datasets" {
  bucket = aws_s3_bucket.datasets.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datasets" {
  bucket = aws_s3_bucket.datasets.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "datasets" {
  bucket = aws_s3_bucket.datasets.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "datasets" {
  bucket = aws_s3_bucket.datasets.id

  rule {
    id     = "expire-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
