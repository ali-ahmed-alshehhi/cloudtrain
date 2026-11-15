# ECR repositories — one per service image (Salem pushes here).
# Owners: Hamda + Fatma.

resource "aws_ecr_repository" "services" {
  for_each = toset(var.repository_names)

  name                 = "cloudtrain/${var.environment}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment == "dev"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name    = each.value
    Purpose = "container-image"
  }
}
