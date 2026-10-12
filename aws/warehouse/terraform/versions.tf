# Phase 6 analytics stack: DynamoDB zero-ETL -> Redshift Serverless -> star schema (scheduled procedure) -> QuickSight.
# Code only: nothing here has been applied (no AWS calls were made). CI runs `terraform validate` (no credentials needed).
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}
