# CDC path (ADR 0005, docs/migration/cdc.md): RDS SQL Server CDC -> DMS (cdc task, full before/after images) ->
# Kinesis Data Streams -> Lambda (cdc/lambda/handler.py, mapping-driven transform) -> DynamoDB, SQS DLQ.
# The task is created stopped; scripts/aws/start-cdc.sh starts it at the time captured before the bulk load.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "subnet_ids" { type = list(string) }
variable "vpc_id" { type = string }
variable "sql_address" { type = string }
variable "sql_port" { type = number }
variable "sql_username" { type = string }
variable "sql_password" {
  type      = string
  sensitive = true
}
variable "table_arns" { type = map(string) }
variable "kms_key_arns" { type = map(string) }
variable "dms_instance_class" { type = string }
variable "kinesis_shards" { type = number }
variable "lambda_zip" { type = string }
variable "create_dms_service_roles" {
  description = "dms-vpc-role / dms-cloudwatch-logs-role are account-wide with fixed names: create them once per account."
  type        = bool
  default     = true
}
variable "dms_config_dir" {
  description = "aws/dms in the repo (table mappings, task settings)."
  type        = string
}

data "aws_partition" "p" {}

# ---------------- Kinesis ----------------
resource "aws_kinesis_stream" "cdc" {
  name             = "${var.name}-cdc"
  retention_period = 24
  encryption_type  = "KMS"
  kms_key_id       = "alias/aws/kinesis"
  stream_mode_details { stream_mode = "PROVISIONED" }
  shard_count = var.kinesis_shards
}

# ---------------- DMS ----------------
data "aws_iam_policy_document" "dms_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["dms.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dms_vpc" {
  count              = var.create_dms_service_roles ? 1 : 0
  name               = "dms-vpc-role"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

resource "aws_iam_role_policy_attachment" "dms_vpc" {
  count      = var.create_dms_service_roles ? 1 : 0
  role       = aws_iam_role.dms_vpc[0].name
  policy_arn = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AmazonDMSVPCManagementRole"
}

resource "aws_iam_role" "dms_logs" {
  count              = var.create_dms_service_roles ? 1 : 0
  name               = "dms-cloudwatch-logs-role"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

resource "aws_iam_role_policy_attachment" "dms_logs" {
  count      = var.create_dms_service_roles ? 1 : 0
  role       = aws_iam_role.dms_logs[0].name
  policy_arn = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AmazonDMSCloudWatchLogsRole"
}

resource "aws_iam_role" "dms_kinesis" {
  name               = "${var.name}-dms-kinesis"
  assume_role_policy = data.aws_iam_policy_document.dms_assume.json
}

resource "aws_iam_role_policy" "dms_kinesis" {
  name = "put-records"
  role = aws_iam_role.dms_kinesis.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["kinesis:DescribeStream", "kinesis:PutRecord", "kinesis:PutRecords"],
    Resource = aws_kinesis_stream.cdc.arn }]
  })
}

resource "aws_dms_replication_subnet_group" "cdc" {
  replication_subnet_group_id          = "${var.name}-dms"
  replication_subnet_group_description = "${var.name} DMS"
  subnet_ids                           = var.subnet_ids
  depends_on                           = [aws_iam_role_policy_attachment.dms_vpc]
}

resource "aws_security_group" "dms" {
  name        = "${var.name}-dms"
  description = "DMS replication instance (egress only)"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_dms_replication_instance" "cdc" {
  replication_instance_id     = "${var.name}-cdc"
  replication_instance_class  = var.dms_instance_class
  allocated_storage           = 20
  multi_az                    = false
  publicly_accessible         = false
  replication_subnet_group_id = aws_dms_replication_subnet_group.cdc.id
  vpc_security_group_ids      = [aws_security_group.dms.id]
  apply_immediately           = true
}

# aws/dms/sqlserver-source-endpoint.json, as endpoint attributes
resource "aws_dms_endpoint" "source" {
  endpoint_id                 = "${var.name}-sqlserver-source"
  endpoint_type               = "source"
  engine_name                 = "sqlserver"
  server_name                 = var.sql_address
  port                        = var.sql_port
  username                    = var.sql_username
  password                    = var.sql_password
  database_name               = "AdventureWorks2022"
  ssl_mode                    = "require"
  extra_connection_attributes = "safeguardPolicy=RELY_ON_SQL_SERVER_REPLICATION_AGENT;tlogAccessMode=PreferTlog;readBackupOnly=false"
}

# aws/dms/kinesis-endpoint.json
resource "aws_dms_endpoint" "kinesis" {
  endpoint_id   = "${var.name}-kinesis-target"
  endpoint_type = "target"
  engine_name   = "kinesis"
  kinesis_settings {
    stream_arn                     = aws_kinesis_stream.cdc.arn
    message_format                 = "json"
    service_access_role_arn        = aws_iam_role.dms_kinesis.arn
    include_transaction_details    = true
    include_partition_value        = true
    partition_include_schema_table = true
    include_table_alter_operations = false
    include_control_details        = false
    include_null_and_empty         = true
  }
  # NoHexPrefix (binary columns without "0x", aws/dms/kinesis-endpoint.json) is not exposed in the provider's
  # kinesis_settings block; passed as an extra connection attribute (verify on first apply, see docs/aws-setup.md).
  extra_connection_attributes = "NoHexPrefix=true"
}

locals {
  task_settings = { for k, v in jsondecode(file("${var.dms_config_dir}/task-settings.json")) : k => v if k != "_comment" }
}

resource "aws_dms_replication_task" "cdc" {
  replication_task_id       = "${var.name}-oltp-to-kinesis"
  migration_type            = "cdc"
  replication_instance_arn  = aws_dms_replication_instance.cdc.replication_instance_arn
  source_endpoint_arn       = aws_dms_endpoint.source.endpoint_arn
  target_endpoint_arn       = aws_dms_endpoint.kinesis.endpoint_arn
  table_mappings            = file("${var.dms_config_dir}/table-mappings.json")
  replication_task_settings = jsonencode(local.task_settings)
  start_replication_task    = false # started by scripts/aws/start-cdc.sh with --cdc-start-time (after CDC is enabled)
  lifecycle {
    ignore_changes = [replication_task_settings, cdc_start_time, cdc_start_position]
  }
}

# ---------------- Lambda ----------------
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-cdc-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role" "lambda" {
  name = "${var.name}-cdc-lambda"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_kinesis" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:${data.aws_partition.p.partition}:iam::aws:policy/service-role/AWSLambdaKinesisExecutionRole"
}

resource "aws_iam_role_policy" "lambda" {
  name = "cdc-transform"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:PutItem",
        "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"],
      Resource = flatten([for a in values(var.table_arns) : [a, "${a}/index/*"]]) },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.dlq.arn }
      ], length(var.kms_key_arns) == 0 ? [] : [
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"], Resource = values(var.kms_key_arns) }
    ])
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}-cdc-transform"
  retention_in_days = 14
}

resource "aws_lambda_function" "cdc" {
  function_name    = "${var.name}-cdc-transform"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "handler.handler"
  filename         = var.lambda_zip # dist/aw-cdc-lambda.zip from cdc/lambda/build.sh
  source_code_hash = try(filebase64sha256(var.lambda_zip), null)
  memory_size      = 512
  timeout          = 60
  environment {
    variables = {
      CDC_LOOKUP_ATTEMPTS   = "4"
      CDC_LOOKUP_BACKOFF_MS = "100"
    }
  }
  depends_on = [aws_cloudwatch_log_group.lambda]
}

# cdc/lambda/handler.py docstring: partial batch failures, bisect, 5 retries, DLQ, one batch per shard at a time.
resource "aws_lambda_event_source_mapping" "kinesis" {
  event_source_arn                   = aws_kinesis_stream.cdc.arn
  function_name                      = aws_lambda_function.cdc.arn
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 100
  maximum_batching_window_in_seconds = 1
  parallelization_factor             = 1
  bisect_batch_on_function_error     = true
  maximum_retry_attempts             = 5
  function_response_types            = ["ReportBatchItemFailures"]
  destination_config {
    on_failure { destination_arn = aws_sqs_queue.dlq.arn }
  }
}

output "kinesis_stream_arn" { value = aws_kinesis_stream.cdc.arn }
output "replication_task_arn" { value = aws_dms_replication_task.cdc.replication_task_arn }
output "lambda_name" { value = aws_lambda_function.cdc.function_name }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
output "dms_security_group_id" { value = aws_security_group.dms.id }
