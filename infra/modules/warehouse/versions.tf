# Phase 6 analytics stack as a module of the phase 7 root (infra/live): DynamoDB zero-ETL -> Redshift Serverless ->
# star schema (scheduled procedure) -> optional QuickSight. Provider configuration lives in the root module.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}
data "aws_region" "r" {}
