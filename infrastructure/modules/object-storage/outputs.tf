output "datasets_bucket_name" {
  value = aws_s3_bucket.datasets.id
}

output "datasets_bucket_arn" {
  value = aws_s3_bucket.datasets.arn
}

output "artifacts_bucket_name" {
  value = aws_s3_bucket.artifacts.id
}

output "artifacts_bucket_arn" {
  value = aws_s3_bucket.artifacts.arn
}
