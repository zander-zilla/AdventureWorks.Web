# Offline plan tests (terraform test + mock providers): no AWS credentials, nothing created. Run in CI (infra workflow).
mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1", name = "us-east-1" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}
mock_provider "random" {}

variables {
  env           = "ci"
  allowed_cidrs = ["203.0.113.10/32"]
}

run "demo_full_stack" {
  command = plan
  variables {
    enable_source = true
  }
  # W-1: AWS-owned keys (SSE disabled) on five tables, CMKs on the two PII tables
  assert {
    condition     = length(module.dynamodb.kms_key_arns) == 2
    error_message = "expected CMKs on aw-customer and aw-hr only"
  }
  assert {
    condition     = length(module.cdc) == 1 && length(module.source_db) == 1
    error_message = "source + CDC expected in the full stack"
  }
  assert {
    condition     = length(module.warehouse.integration_ids) == 7
    error_message = "one zero-ETL integration per domain table"
  }
}

run "dynamodb_encryption_per_table" {
  command = plan
  module {
    source = "../modules/dynamodb"
  }
  variables {
    name       = "aw-ci"
    tables     = { "aw-catalog" = ["GSI1", "GSI2"], "aw-customer" = ["GSI1", "GSI2"], "aw-hr" = ["GSI1", "GSI2"], "aw-reference" = ["GSI1"] }
    cmk_tables = ["aw-customer", "aw-hr"]
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-catalog"].server_side_encryption[0].enabled == false
    error_message = "aw-catalog must use the AWS-owned key (SSE disabled), not the AWS-managed key"
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-hr"].server_side_encryption[0].enabled == true
    error_message = "aw-hr must use its CMK"
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-reference"].point_in_time_recovery[0].enabled
    error_message = "PITR is a zero-ETL prerequisite"
  }
  assert {
    condition     = length(aws_dynamodb_table.t["aw-reference"].global_secondary_index) == 1
    error_message = "aw-reference has GSI1 only"
  }
}

run "dev_without_source_or_quicksight" {
  command = plan
  variables {
    enable_source            = false
    create_dms_service_roles = false
  }
  assert {
    condition     = length(module.cdc) == 0 && length(module.source_db) == 0 && output.before_url == null
    error_message = "enable_source=false must drop RDS/DMS/Kinesis/Lambda and the before app"
  }
}

run "quicksight_toggle" {
  command = plan
  variables {
    enable_source            = false
    enable_quicksight        = true
    quicksight_principal_arn = "arn:aws:quicksight:us-east-1:123456789012:user/default/john"
  }
  assert {
    condition     = module.warehouse.quicksight_enabled
    error_message = "QuickSight data set expected when enable_quicksight = true"
  }
}

run "quicksight_requires_principal" {
  command = plan
  variables {
    enable_quicksight = true
  }
  expect_failures = [var.quicksight_principal_arn]
}

run "budget_alert" {
  command = plan
  variables {
    budget_alert_emails = ["ops@example.com"]
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 1 && aws_budgets_budget.monthly[0].limit_amount == "50"
    error_message = "USD 50/month budget expected when an alert e-mail is set"
  }
}

run "no_budget_without_email" {
  command = plan
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "no budget without alert e-mails"
  }
}
