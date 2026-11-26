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
  vpc_cidr    = module.networking[0].vpc_cidr
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

# Cognito login (decision 0006). Module lives in modules/identity (from Salem #121); wired here.
module "identity" {
  count  = var.enable_identity ? 1 : 0
  source = "./modules/identity"

  environment                = var.environment
  aws_region                 = var.aws_region
  issuer_base_url            = var.use_emulator ? var.emulator_endpoint : ""
  allow_admin_password_login = var.use_emulator
  deletion_protection        = var.environment == "staging"
}

module "iam" {
  count  = var.enable_training_compute || var.enable_ecs_roles ? 1 : 0
  source = "./modules/iam"

  environment          = var.environment
  datasets_bucket_arn  = module.object_storage.datasets_bucket_arn
  artifacts_bucket_arn = module.object_storage.artifacts_bucket_arn
  job_events_queue_arn = module.message_queue.job_events_queue_arn

  # ECS task execution role + GitHub OIDC deploy role (modules/iam/ecs.tf, Salem)
  enable_ecs_roles    = var.enable_ecs_roles
  aws_region          = var.aws_region
  ecr_repository_arns = var.enable_container_registry ? values(module.container_registry[0].repository_arns) : []
  ecs_cluster_name    = "${var.environment}-cloudtrain"
  # Each service's OWN database secret (scripts/bootstrap-schemas.sh), never the master secret
  secret_names = var.enable_service_roles ? [for name in values(module.service_roles[0].database_secret_names) : name if name != null] : []
  # The deploy role may pass exactly these per-service task roles (plus the execution role) to ECS
  task_role_arns = var.enable_service_roles ? values(module.service_roles[0].task_role_arns) : []
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
  enable_load_balancer  = var.enable_worker_load_balancers
  vpc_id                = module.networking[0].vpc_id

  worker_env = {
    JOB_EVENTS_QUEUE_URL = module.message_queue.job_events_queue_url
    DATASETS_BUCKET      = module.object_storage.datasets_bucket_name
    ARTIFACTS_BUCKET     = module.object_storage.artifacts_bucket_name
  }
}

# One task role per service (security/DEPLOYMENT_POLICY.md). Used by the ECS services in #36.
module "service_roles" {
  count  = var.enable_service_roles ? 1 : 0
  source = "./modules/service-roles"

  environment             = var.environment
  datasets_bucket_arn     = module.object_storage.datasets_bucket_arn
  artifacts_bucket_arn    = module.object_storage.artifacts_bucket_arn
  training_jobs_queue_arn = module.message_queue.training_jobs_queue_arn
  training_jobs_dlq_arn   = module.message_queue.training_jobs_dlq_arn
  job_events_queue_arn    = module.message_queue.job_events_queue_arn
}

# Multi-GPU workers (#36): the same module, a machine with 4 GPUs for Ahmed + Abdulla's DDP runs.
# contracts/pricing.yaml has no 2-GPU machine, so a 2-GPU job runs here (and pays for the machine).
module "training_compute_multi_gpu" {
  count  = var.enable_training_compute ? 1 : 0
  source = "./modules/training-compute"

  environment           = var.environment
  pool_name             = "gpu-4"
  instance_type         = var.multi_gpu_instance_type
  ami_id                = var.worker_ami_id
  subnet_ids            = module.networking[0].private_subnet_ids
  security_group_ids    = [var.enable_security_groups ? module.security[0].workers_security_group_id : module.networking[0].default_security_group_id]
  instance_profile_name = module.iam[0].worker_instance_profile_name
  desired_capacity      = var.multi_gpu_desired_capacity
  min_size              = 0
  max_size              = var.multi_gpu_max_size
  enable_load_balancer  = var.enable_worker_load_balancers
  vpc_id                = module.networking[0].vpc_id

  worker_env = {
    JOB_EVENTS_QUEUE_URL = module.message_queue.job_events_queue_url
    DATASETS_BUCKET      = module.object_storage.datasets_bucket_name
    ARTIFACTS_BUCKET     = module.object_storage.artifacts_bucket_name
  }
}

# CloudWatch log groups (one per ECS service) and alarms (#36). Alarms follow monitoring/aws/README.md.
module "monitoring" {
  count  = var.enable_monitoring ? 1 : 0
  source = "./modules/monitoring"

  environment           = var.environment
  training_jobs_dlq_arn = module.message_queue.training_jobs_dlq_arn
  job_events_queue_arn  = module.message_queue.job_events_queue_arn
  log_retention_days    = var.log_retention_days
  # Plan-time switch (alb_arn_suffix is only known after apply, so it cannot drive count).
  create_server_errors_alarm = var.enable_application_services
  alb_arn_suffix             = length(module.application_services) > 0 ? module.application_services[0].alb_arn_suffix : null
}

# Same paths monitoring creates — pass by name so ECS does not create the groups twice.
locals {
  ecs_log_group_names = {
    for name in [
      "gateway",
      "portal",
      "project-service",
      "dataset-service",
      "job-service",
      "scheduler",
      "model-registry",
      "inference-service",
      "mlflow",
      "job-events-monitor",
    ] : name => "/cloudtrain/${var.environment}/${name}"
  }
}

# ECS Fargate + public ALB (#36). Cluster name <environment>-cloudtrain matches #129.
module "application_services" {
  count  = var.enable_application_services ? 1 : 0
  source = "./modules/application-services"

  environment        = var.environment
  aws_region         = var.aws_region
  vpc_id             = module.networking[0].vpc_id
  public_subnet_ids  = module.networking[0].public_subnet_ids
  private_subnet_ids = module.networking[0].private_subnet_ids

  alb_security_group_id      = var.enable_security_groups ? module.security[0].alb_security_group_id : ""
  services_security_group_id = var.enable_security_groups ? module.security[0].services_security_group_id : ""
  default_security_group_id  = module.networking[0].default_security_group_id

  execution_role_arn  = module.iam[0].ecs_task_execution_role_arn
  task_role_arns      = module.service_roles[0].task_role_arns
  ecr_repository_urls = module.container_registry[0].repository_urls
  image_tag           = var.ecs_image_tag
  desired_count       = var.ecs_desired_count

  # Prefer monitoring's groups when enabled; otherwise this module creates them.
  log_group_names = var.enable_monitoring ? local.ecs_log_group_names : {}

  database_secret_names = module.service_roles[0].database_secret_names

  datasets_bucket         = module.object_storage.datasets_bucket_name
  artifacts_bucket        = module.object_storage.artifacts_bucket_name
  training_jobs_queue_url = module.message_queue.training_jobs_queue_url
  training_jobs_dlq_url   = module.message_queue.training_jobs_dlq_url
  job_events_queue_url    = module.message_queue.job_events_queue_url

  jwt_issuer   = try(module.identity[0].issuer, "")
  jwt_audience = try(module.identity[0].portal_client_id, "")
  jwt_jwks_url = try(module.identity[0].jwks_url, "")

  # Fatma's worker LBs (#133): machine type → URL for the scheduler.
  worker_urls_json = var.enable_training_compute && var.enable_worker_load_balancers ? jsonencode({
    (var.gpu_instance_type)       = module.training_compute_gpu[0].worker_url
    (var.multi_gpu_instance_type) = module.training_compute_multi_gpu[0].worker_url
  }) : ""

  # Emulator may lack Cloud Map; real AWS keeps it on.
  enable_service_discovery = var.enable_ecs_service_discovery
}
