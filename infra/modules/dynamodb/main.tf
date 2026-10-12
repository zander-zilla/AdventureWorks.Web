# The seven domain tables (docs/design/dynamodb-design.md, design/mapping/mapping.yaml `tables` + `table_settings`).
# Encryption (decision W-1, amends ADR 0004 P3-2): AWS-owned key on catalog/inventory/sales/purchasing/reference
# (server_side_encryption disabled = AWS-owned key, no cost, zero-ETL compatible); customer-managed keys on aw-hr and
# aw-customer (PII, pay, national id) with key-policy statements that let Redshift zero-ETL decrypt them.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "tables" {
  description = "table name => list of GSI names (from mapping.yaml)"
  type        = map(list(string))
}
variable "cmk_tables" {
  description = "Tables encrypted with their own customer-managed KMS key; all others use the AWS-owned key."
  type        = list(string)
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "admin_role_arns" {
  description = "Extra principals allowed to administer the CMKs (the account root is always allowed)."
  type        = list(string)
  default     = []
}

data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}
data "aws_region" "r" {}

locals {
  account = data.aws_caller_identity.me.account_id
  part    = data.aws_partition.p.partition
  region  = data.aws_region.r.region
}

data "aws_iam_policy_document" "cmk" {
  statement {
    sid       = "AccountAdmin"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = concat(["arn:${local.part}:iam::${local.account}:root"], var.admin_role_arns)
    }
  }
  # Redshift zero-ETL: decrypt the exported source table (DynamoDB developer guide, zero-ETL prerequisites).
  statement {
    sid       = "AllowRedshiftZeroEtlDecrypt"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.part}:redshift:${local.region}:${local.account}:integration:*"]
    }
  }
  statement {
    sid       = "AllowRedshiftZeroEtlGrant"
    actions   = ["kms:CreateGrant"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "kms:GrantOperations"
      values   = ["Decrypt", "GenerateDataKey", "CreateGrant", "DescribeKey"]
    }
  }
}

resource "aws_kms_key" "table" {
  for_each                = toset(var.cmk_tables)
  description             = "${var.name} DynamoDB ${each.key} (PII) - customer-managed, zero-ETL grant for Redshift"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.cmk.json
}

resource "aws_kms_alias" "table" {
  for_each      = aws_kms_key.table
  name          = "alias/${var.name}-${each.key}"
  target_key_id = each.value.key_id
}

resource "aws_dynamodb_table" "t" {
  for_each                    = var.tables
  name                        = each.key
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  stream_enabled              = true
  stream_view_type            = "NEW_AND_OLD_IMAGES"
  deletion_protection_enabled = var.deletion_protection

  dynamic "attribute" {
    for_each = concat(["PK", "SK"], flatten([for g in each.value : ["${g}PK", "${g}SK"]]))
    content {
      name = attribute.value
      type = "S"
    }
  }

  dynamic "global_secondary_index" {
    for_each = each.value
    content {
      name            = global_secondary_index.value
      hash_key        = "${global_secondary_index.value}PK"
      range_key       = "${global_secondary_index.value}SK"
      projection_type = "ALL" # P3-3
    }
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery { enabled = true } # zero-ETL prerequisite

  # enabled = false -> AWS-owned key; enabled = true + kms_key_arn -> customer-managed key. Never the AWS-managed key.
  server_side_encryption {
    enabled     = contains(var.cmk_tables, each.key)
    kms_key_arn = contains(var.cmk_tables, each.key) ? aws_kms_key.table[each.key].arn : null
  }
}

output "table_arns" { value = { for k, t in aws_dynamodb_table.t : k => t.arn } }
output "kms_key_arns" { value = { for k, v in aws_kms_key.table : k => v.arn } }
