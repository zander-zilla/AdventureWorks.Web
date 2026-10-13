# Whole AdventureWorks AWS deployment (Phase 7). See docs/aws-setup.md (runbook) and ADR 0008.
locals {
  name    = "aw-${var.env}"
  mapping = jsondecode(file("${path.module}/../../design/mapping/mapping.json"))
  tables  = { for t, v in local.mapping.tables : t => v.gsis }
}

module "network" {
  source = "../modules/network"
  name   = local.name
  cidr   = var.vpc_cidr
}

module "dynamodb" {
  source              = "../modules/dynamodb"
  name                = local.name
  tables              = local.tables
  cmk_tables          = var.cmk_tables
  deletion_protection = var.deletion_protection
}

module "source_db" {
  count          = var.enable_source ? 1 : 0
  source         = "../modules/source_db"
  name           = local.name
  vpc_id         = module.network.vpc_id
  vpc_cidr       = module.network.cidr
  subnet_ids     = module.network.private_subnet_ids
  instance_class = var.sql_instance_class
}

module "cdc" {
  count                    = var.enable_source ? 1 : 0
  source                   = "../modules/cdc"
  name                     = local.name
  vpc_id                   = module.network.vpc_id
  subnet_ids               = module.network.private_subnet_ids
  sql_address              = module.source_db[0].address
  sql_port                 = module.source_db[0].port
  sql_username             = module.source_db[0].username
  sql_password             = module.source_db[0].password
  table_arns               = module.dynamodb.table_arns
  kms_key_arns             = module.dynamodb.kms_key_arns
  dms_instance_class       = var.dms_instance_class
  kinesis_shards           = var.kinesis_shards
  lambda_zip               = var.lambda_zip
  monitor_api_zip          = var.monitor_api_zip
  enable_monitor_api       = var.enable_showcase && var.enable_monitor_api
  create_dms_service_roles = var.create_dms_service_roles
  dms_config_dir           = "${path.module}/../../aws/dms"
}

module "app" {
  source                = "../modules/app"
  name                  = local.name
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  allowed_cidrs         = var.allowed_cidrs
  certificate_arn       = local.certificate_arn
  enable_https          = local.https
  domain_name           = var.domain_name
  image_tag             = var.image_tag
  desired_count         = var.app_desired_count
  enable_before_app     = var.enable_source && var.enable_before_app
  has_source            = var.enable_source
  table_arns            = module.dynamodb.table_arns
  kms_key_arns          = module.dynamodb.kms_key_arns
  sql_secret_arn        = var.enable_source ? module.source_db[0].secret_arn : ""
  sql_security_group_id = var.enable_source ? module.source_db[0].security_group_id : ""
  backups_bucket        = var.enable_source ? module.source_db[0].backups_bucket : ""
  frame_ancestors       = var.enable_showcase ? module.showcase[0].origin : ""
  ai_environment        = var.enable_ai ? module.ai[0].environment : []
  ai_policy_json        = var.enable_ai ? module.ai[0].policy_json : ""
}

# C2-5 Bedrock AI layer (off by default; costs per request + S3 Vectors storage).
module "ai" {
  count              = var.enable_ai ? 1 : 0
  source             = "../modules/ai"
  name               = local.name
  redshift_workgroup = module.warehouse.workgroup
  competitor_words   = var.ai_competitor_words
}

# Phase 8 showcase (ADR 0009): static site on S3 + CloudFront; content via scripts/aws/push-showcase.sh.
module "showcase" {
  count                = var.enable_showcase ? 1 : 0
  source               = "../modules/showcase"
  name                 = local.name
  enable_monitor_api   = local.monitor_api
  monitor_api_url      = local.monitor_api ? module.cdc[0].monitor_api_url : ""
  monitor_api_function = local.monitor_api ? module.cdc[0].monitor_api_function : ""
}

locals {
  monitor_api = var.enable_showcase && var.enable_source && var.enable_monitor_api
}

resource "aws_security_group" "redshift" {
  name        = "${local.name}-redshift"
  description = "Redshift Serverless workgroup (QuickSight / Data API reach it through the service)"
  vpc_id      = module.network.vpc_id
  ingress {
    from_port   = 5439
    to_port     = 5439
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

module "warehouse" {
  source                   = "../modules/warehouse"
  name                     = local.name
  dynamodb_table_arns      = module.dynamodb.table_arns
  subnet_ids               = module.network.private_subnet_ids
  security_group_ids       = [aws_security_group.redshift.id]
  base_capacity_rpu        = var.redshift_base_rpu
  max_capacity_rpu         = var.redshift_max_rpu
  monthly_rpu_hours_limit  = var.redshift_monthly_rpu_hours_limit
  build_schedule           = var.star_build_schedule
  enable_quicksight        = var.enable_quicksight
  quicksight_principal_arn = var.quicksight_principal_arn
}
