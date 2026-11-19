# ECR repositories — one per service image (Salem pushes here).
# Owners: Hamda + Fatma.

resource "aws_ecr_repository" "services" {
  # checkov:skip=CKV_AWS_136: AES256 default encryption OK for lab; KMS with Salem later
  for_each = toset(var.repository_names)

  name                 = "cloudtrain/${var.environment}/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.environment == "dev"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name    = each.value
    Purpose = "container-image"
  }
}

# Keep the last 20 images per repository, so a rollback still has the previous images.
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}
