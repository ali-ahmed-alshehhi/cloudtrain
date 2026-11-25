output "state_bucket_name" {
  description = "Put this in `bucket = ...` in infrastructure/backends/<env>.s3.backend.hcl."
  value       = aws_s3_bucket.state.bucket
}

output "state_bucket_arn" {
  description = "For IAM policies that allow the Terraform role to read and write state (with Salem)."
  value       = aws_s3_bucket.state.arn
}

output "state_bucket_region" {
  description = "Put this in `region = ...` in the backend .hcl file."
  value       = var.aws_region
}
