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
  count  = var.enable_networking && var.enable_security_groups ? 1 : 0
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

module "database" {
  count  = var.enable_database ? 1 : 0
  source = "./modules/database"

  environment        = var.environment
  project            = var.project
  private_subnet_ids = module.networking[0].private_subnet_ids
  # Without our own security groups (the emulator, see enable_security_groups), the database
  # sits in the VPC's default security group, which networking locks down (no rules).
  database_security_group_id = var.enable_security_groups ? module.security[0].database_security_group_id : module.networking[0].default_security_group_id
  instance_class             = var.db_instance_class
  multi_az                   = var.db_multi_az
  deletion_protection        = var.db_deletion_protection
}

module "iam" {
  count  = var.enable_training_compute ? 1 : 0
  source = "./modules/iam"

  environment          = var.environment
  datasets_bucket_arn  = module.object_storage.datasets_bucket_arn
  artifacts_bucket_arn = module.object_storage.artifacts_bucket_arn
  job_events_queue_arn = module.message_queue.job_events_queue_arn
}

module "training_compute_gpu" {
  count  = var.enable_training_compute ? 1 : 0
  source = "./modules/training-compute"

  environment   = var.environment
  pool_name     = "gpu-1"
  instance_type = var.gpu_instance_type
  ami_id        = var.worker_ami_id
  subnet_ids    = module.networking[0].private_subnet_ids
  # Without our own security groups (the emulator), workers use the VPC's locked-down default group.
  security_group_ids    = [var.enable_security_groups ? module.security[0].workers_security_group_id : module.networking[0].default_security_group_id]
  instance_profile_name = module.iam[0].worker_instance_profile_name
  desired_capacity      = var.worker_desired_capacity
  min_size              = 0
  max_size              = var.worker_max_size

  worker_env = {
    JOB_EVENTS_QUEUE_URL = module.message_queue.job_events_queue_url
    DATASETS_BUCKET      = module.object_storage.datasets_bucket_name
    ARTIFACTS_BUCKET     = module.object_storage.artifacts_bucket_name
  }
}
