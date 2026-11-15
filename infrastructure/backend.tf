# State backend.
# Owners: Hamda + Fatma.
#
# Default = local file (safe for LocalStack practice, no AWS account needed).
# For real AWS, replace this block with the S3 backend in
# backends/s3.backend.tf.example and run:
#   terraform init -migrate-state -backend-config=backends/dev.s3.backend.hcl

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
