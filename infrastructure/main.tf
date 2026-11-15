# CloudTrain root module — wires Student 6 modules together.
# Owners: Hamda + Fatma.

module "networking" {
  count  = var.enable_networking ? 1 : 0
  source = "./modules/networking"

  environment        = var.environment
  availability_zones = var.availability_zones
  enable_nat         = !var.use_localstack
}

module "security" {
  count  = var.enable_networking ? 1 : 0
  source = "./modules/security"

  environment = var.environment
  vpc_id      = module.networking[0].vpc_id
}

module "object_storage" {
  source = "./modules/object-storage"

  datasets_bucket_name  = var.datasets_bucket_name
  artifacts_bucket_name = var.artifacts_bucket_name
}

module "message_queue" {
  source = "./modules/message-queue"

  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  max_receive_count          = var.sqs_max_receive_count
}

module "container_registry" {
  count  = var.enable_container_registry ? 1 : 0
  source = "./modules/container-registry"

  environment = var.environment
}
