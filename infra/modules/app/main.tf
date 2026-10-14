# App hosting (ADR 0008): ECS Fargate behind an ALB.
#  - "after": the .NET 10 app (docker/after/Dockerfile, chiseled non-root) reading/writing DynamoDB with its task role.
#  - "before" (optional): the original app (docker/before/Dockerfile.app) on SQL Server, for the live CDC demo.
#  - "tools" task definition (docker/tools/Dockerfile): one-off db init (restore + CDC) and bulk load inside the VPC.
# Tasks run in public subnets with public IPs (no NAT gateway); their security group only admits the ALB.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "allowed_cidrs" { type = list(string) }
variable "certificate_arn" {
  type    = string
  default = ""
}
variable "enable_https" {
  description = "HTTPS listeners (443 after, 8080 before) with certificate_arn (required when true). Known at plan time even when the ACM certificate is created in the same apply."
  type        = bool
  default     = false
}
variable "domain_name" {
  description = "Public host name of the ALB (ACM certificate / Route 53 alias); empty = the ALB DNS name."
  type        = string
  default     = ""
}
variable "image_tag" { type = string }
variable "desired_count" { type = number }
variable "enable_before_app" { type = bool }
variable "table_arns" { type = map(string) }
variable "kms_key_arns" { type = map(string) }
variable "sql_secret_arn" { type = string }
variable "has_source" {
  description = "SQL Server source deployed (before app / tools task get the SQL secret and SG access)."
  type        = bool
}
variable "sql_security_group_id" { type = string }
variable "backups_bucket" { type = string }
variable "frame_ancestors" {
  description = "Origins allowed to embed the .NET 10 app (the Phase 8 showcase); empty = X-Frame-Options SAMEORIGIN."
  type        = string
  default     = ""
}

variable "ai_environment" {
  description = "C2-5: Ai__* settings from module ai (empty = AI layer off)."
  type        = list(object({ name = string, value = string }))
  default     = []
}
variable "ai_policy_json" {
  description = "C2-5: IAM policy for Bedrock, S3 Vectors and the Redshift Data API (empty = AI layer off)."
  type        = string
  default     = ""
}

variable "synthetic_data" {
  description = "C2-7: generated data 2014-07 .. today is loaded (offers are then priced as of today instead of 2014-05-01)."
  type        = bool
  default     = false
}
variable "synthetic_trickle" {
  description = "C2-7: daily trickle job (EventBridge Scheduler -> tools task 'synthetic-trickle'), generates the missed days up to yesterday."
  type        = bool
  default     = false
}
variable "synthetic_trickle_schedule" {
  description = "C2-7: when the trickle runs (UTC)."
  type        = string
  default     = "cron(30 2 * * ? *)"
}

data "aws_region" "r" {}
data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}

locals {
  region = data.aws_region.r.region
  https  = var.enable_https # a known bool: certificate_arn may be unknown until the ACM certificate is validated
  host   = var.domain_name != "" ? var.domain_name : aws_lb.app.dns_name
  repos  = toset(concat(["after", "tools"], var.enable_before_app ? ["before"] : []))
}

resource "aws_ecr_repository" "r" {
  for_each             = local.repos
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # teardown
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "r" {
  for_each   = aws_ecr_repository.r
  repository = each.value.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "keep 10", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }, action = { type = "expire" } }] })
}

resource "aws_ecs_cluster" "c" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "disabled" # cost; enable for load tests
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 14
}

# ---------------- IAM ----------------
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secret" {
  count  = var.has_source ? 1 : 0
  name   = "sql-secret"
  role   = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.sql_secret_arn }] })
}

locals {
  ddb_rw = flatten([for a in values(var.table_arns) : [a, "${a}/index/*"]])
  kms    = length(var.kms_key_arns) == 0 ? [] : [{ Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"], Resource = values(var.kms_key_arns) }]
}

resource "aws_iam_role" "after" {
  name               = "${var.name}-after-app"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# The .NET 10 app touches aw-catalog, aw-customer, aw-sales (ADR 0006); C2-2 adds aw-inventory (ship: stock +
# TransactionHistory, one transaction with aw-sales) and aw-reference (read-only: tax rates, ship methods); C2-3 adds
# aw-purchasing (vendors, purchase orders; Scan for the cached vendor list).
resource "aws_iam_role_policy" "after" {
  name = "dynamodb"
  role = aws_iam_role.after.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([{ Effect = "Allow",
      Action = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:DeleteItem", "dynamodb:BatchWriteItem", "dynamodb:Scan", "dynamodb:TransactWriteItems", "dynamodb:ConditionCheckItem", "dynamodb:DescribeTable"],
      Resource = flatten([for t in ["aw-catalog", "aw-customer", "aw-sales", "aw-inventory", "aw-reference", "aw-purchasing"] : [var.table_arns[t], "${var.table_arns[t]}/index/*"]])
    }], local.kms)
  })
}

resource "aws_iam_role_policy" "ai" {
  count  = var.ai_policy_json == "" ? 0 : 1
  name   = "ai"
  role   = aws_iam_role.after.id
  policy = var.ai_policy_json
}

resource "aws_iam_role" "tools" {
  name               = "${var.name}-tools"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "tools" {
  name = "bulk-load"
  role = aws_iam_role.tools.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["dynamodb:BatchWriteItem", "dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan",
      "dynamodb:DescribeTable"], Resource = local.ddb_rw },
      { Effect = "Allow", Action = ["dynamodb:ListTables"], Resource = "*" },
      ], local.kms, var.has_source ? [
      # db_init.py stages the AdventureWorks .bak files in the backups bucket for RDS native restore
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      Resource = ["arn:${data.aws_partition.p.partition}:s3:::${var.backups_bucket}", "arn:${data.aws_partition.p.partition}:s3:::${var.backups_bucket}/*"] }
    ] : [])
  })
}

# ---------------- Network ----------------
resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "ALB: HTTP(S) from allowed CIDRs"
  vpc_id      = var.vpc_id
  dynamic "ingress" {
    for_each = toset(concat([80, 8080], local.https ? [443] : []))
    content {
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = var.allowed_cidrs
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "tasks" {
  name        = "${var.name}-tasks"
  description = "Fargate tasks: only from the ALB"
  vpc_id      = var.vpc_id
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "app" {
  name                       = substr("${var.name}-alb", 0, 32)
  load_balancer_type         = "application"
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "after" {
  name        = substr("${var.name}-after", 0, 32)
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/healthz"
    matcher = "200"
  }
  deregistration_delay = 10
}

resource "aws_lb_target_group" "before" {
  count       = var.enable_before_app ? 1 : 0
  name        = substr("${var.name}-before", 0, 32)
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/"
    matcher = "200-399"
  }
  deregistration_delay = 10
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = local.https ? "redirect" : "forward"
    target_group_arn = local.https ? null : aws_lb_target_group.after.arn
    dynamic "redirect" {
      for_each = local.https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = local.https ? 1 : 0
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.after.arn
  }
}

resource "aws_lb_listener" "before" {
  count             = var.enable_before_app ? 1 : 0
  load_balancer_arn = aws_lb.app.arn
  port              = 8080
  protocol          = local.https ? "HTTPS" : "HTTP"
  ssl_policy        = local.https ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
  certificate_arn   = local.https ? var.certificate_arn : null
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.before[0].arn
  }
}

# ---------------- Task definitions + services ----------------
locals {
  log = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.app.name, "awslogs-region" = local.region } }
}

locals {
  app_environment = concat([
    { name = "ASPNETCORE_URLS", value = "http://+:8080" },
    { name = "DynamoDb__Region", value = local.region },
    { name = "Showcase__FrameAncestors", value = var.frame_ancestors },
  ], var.ai_environment, var.synthetic_data ? [{ name = "Pricing__OfferDate", value = "today" }] : [])
}

resource "aws_ecs_task_definition" "after" {
  family                   = "${var.name}-after"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.after.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name                   = "app"
    image                  = "${aws_ecr_repository.r["after"].repository_url}:${var.image_tag}"
    essential              = true
    readonlyRootFilesystem = true
    portMappings           = [{ containerPort = 8080, protocol = "tcp" }]
    environment            = local.app_environment
    logConfiguration       = merge(local.log, { options = merge(local.log.options, { "awslogs-stream-prefix" = "after" }) })
  }])
}

resource "aws_ecs_service" "after" {
  name                              = "after"
  cluster                           = aws_ecs_cluster.c.id
  task_definition                   = aws_ecs_task_definition.after.arn
  desired_count                     = var.desired_count
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 30
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true # pulls from ECR / reaches DynamoDB without a NAT gateway
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.after.arn
    container_name   = "app"
    container_port   = 8080
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_task_definition" "before" {
  count                    = var.enable_before_app ? 1 : 0
  family                   = "${var.name}-before"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = "${aws_ecr_repository.r["before"].repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "ASPNETCORE_URLS", value = "http://+:8080" },
      { name = "Showcase__FrameAncestors", value = var.frame_ancestors },
      { name = "DisableHttpsRedirection", value = "true" },
    ]
    # host/username/password come from the secret; the connection string is assembled at start (FullDb derives the
    # AdventureWorks2022 connection from it, decision 1).
    entryPoint = ["/bin/sh", "-c"]
    command    = ["export ConnectionStrings__sampledbContext=\"Server=$SQL_HOST,1433;Database=AdventureWorksLT2022;User Id=$SQL_USER;Password=$MSSQL_SA_PASSWORD;TrustServerCertificate=True\" && exec dotnet AdventureWorks.Web.dll"]
    secrets = [
      { name = "SQL_HOST", valueFrom = "${var.sql_secret_arn}:host::" },
      { name = "SQL_USER", valueFrom = "${var.sql_secret_arn}:username::" },
      { name = "MSSQL_SA_PASSWORD", valueFrom = "${var.sql_secret_arn}:password::" },
    ]
    logConfiguration = merge(local.log, { options = merge(local.log.options, { "awslogs-stream-prefix" = "before" }) })
  }])
}

resource "aws_security_group_rule" "tasks_to_sql" {
  count                    = var.has_source ? 1 : 0
  type                     = "ingress"
  from_port                = 1433
  to_port                  = 1433
  protocol                 = "tcp"
  security_group_id        = var.sql_security_group_id
  source_security_group_id = aws_security_group.tasks.id
  description              = "before app + tools task"
}

resource "aws_ecs_service" "before" {
  count           = var.enable_before_app ? 1 : 0
  name            = "before"
  cluster         = aws_ecs_cluster.c.id
  task_definition = aws_ecs_task_definition.before[0].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.before[0].arn
    container_name   = "app"
    container_port   = 8080
  }
  depends_on = [aws_lb_listener.before]
}

# One-off tasks: `aws ecs run-task ... --overrides` with command ["db-init"] or ["bulk-load"] (scripts/aws/run-tool.sh).
resource "aws_ecs_task_definition" "tools" {
  family                   = "${var.name}-tools"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048
  memory                   = 4096
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.tools.arn
  container_definitions = jsonencode([{
    name      = "tools"
    image     = "${aws_ecr_repository.r["tools"].repository_url}:${var.image_tag}"
    essential = true
    environment = [
      { name = "AWS_REGION", value = local.region },
      { name = "DDB_ENDPOINT", value = "aws" },
      { name = "BACKUPS_BUCKET", value = var.backups_bucket },
      { name = "SQL_PORT", value = "1433" },
    ]
    secrets = var.has_source ? [
      { name = "SQL_HOST", valueFrom = "${var.sql_secret_arn}:host::" },
      { name = "SQL_USER", valueFrom = "${var.sql_secret_arn}:username::" },
      { name = "MSSQL_SA_PASSWORD", valueFrom = "${var.sql_secret_arn}:password::" },
    ] : []
    logConfiguration = merge(local.log, { options = merge(local.log.options, { "awslogs-stream-prefix" = "tools" }) })
  }])
}

# C2-7 daily trickle: EventBridge Scheduler starts the tools task once a day; it inserts the missed days (up to yesterday)
# into SQL Server, and CDC carries them on. Off by default.
resource "aws_iam_role" "trickle" {
  count = var.synthetic_trickle ? 1 : 0
  name  = "${var.name}-synthetic-trickle"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.me.account_id } } }]
  })
}

resource "aws_iam_role_policy" "trickle" {
  count = var.synthetic_trickle ? 1 : 0
  name  = "run-tools-task"
  role  = aws_iam_role.trickle[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecs:RunTask"], Resource = "${aws_ecs_task_definition.tools.arn_without_revision}:*",
      Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.c.arn } } },
      { Effect = "Allow", Action = ["iam:PassRole"], Resource = [aws_iam_role.execution.arn, aws_iam_role.tools.arn] }
    ]
  })
}

resource "aws_scheduler_schedule" "trickle" {
  count               = var.synthetic_trickle ? 1 : 0
  name                = "${var.name}-synthetic-trickle"
  schedule_expression = var.synthetic_trickle_schedule
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_ecs_cluster.c.arn
    role_arn = aws_iam_role.trickle[0].arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.tools.arn_without_revision
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = var.public_subnet_ids
        security_groups  = [aws_security_group.tasks.id]
        assign_public_ip = true
      }
    }
    input = jsonencode({ containerOverrides = [{ name = "tools", command = ["synthetic-trickle"] }] })
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

output "alb_dns" { value = aws_lb.app.dns_name }
output "after_url" { value = "${local.https ? "https" : "http"}://${local.host}/" }
output "before_url" { value = var.enable_before_app ? "${local.https ? "https" : "http"}://${local.host}:8080/" : null }
output "alb_zone_id" { value = aws_lb.app.zone_id }
output "https" { value = local.https }
output "ecr_repositories" { value = { for k, v in aws_ecr_repository.r : k => v.repository_url } }
output "cluster" { value = aws_ecs_cluster.c.name }
output "tools_task_definition" { value = aws_ecs_task_definition.tools.family }
output "tasks_security_group_id" { value = aws_security_group.tasks.id }
output "ai_policy_count" { value = aws_iam_role_policy.ai[*].name }
output "synthetic_trickle_schedule" { value = one(aws_scheduler_schedule.trickle[*].name) }
output "app_environment" { value = local.app_environment }
