# One DynamoDB zero-ETL integration per domain table (an integration has exactly one source table).
# In Redshift each one is materialised with: CREATE DATABASE aw_zetl_<domain> FROM INTEGRATION '<id>'
# (warehouse/sql/redshift/00_setup.sql). Data lands as ("PK", "SK", value SUPER) in DynamoDB JSON.
# Prerequisites on the source tables (infra/modules/dynamodb): PITR enabled and encryption with an AWS-owned key or a
# customer-managed key (AWS-managed keys are not supported). Decision W-1 (ADR 0007): AWS-owned keys on five tables,
# CMKs on aw-hr / aw-customer whose key policies grant redshift.amazonaws.com Decrypt/CreateGrant for integrations.

# Source side: let the Redshift service export from each table.
resource "aws_dynamodb_resource_policy" "zero_etl" {
  for_each     = local.table_arn
  resource_arn = each.value
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowRedshiftZeroEtl"
      Effect    = "Allow"
      Principal = { Service = "redshift.amazonaws.com" }
      Action    = ["dynamodb:ExportTableToPointInTime", "dynamodb:DescribeTable", "dynamodb:DescribeExport"]
      Resource  = "*"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account }
        ArnEquals    = { "aws:SourceArn" = "arn:${local.part}:redshift:${local.region}:${local.account}:integration:*" }
      }
    }]
  })
}

# Target side: authorise the tables as integration sources for the namespace.
resource "aws_redshift_resource_policy" "namespace" {
  resource_arn = aws_redshiftserverless_namespace.aw.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "redshift.amazonaws.com" }
        Action    = "redshift:AuthorizeInboundIntegration"
        Resource  = aws_redshiftserverless_namespace.aw.arn
        Condition = { StringEquals = { "aws:SourceArn" = values(local.table_arn) } }
      },
      {
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.part}:iam::${local.account}:root" }
        Action    = "redshift:CreateInboundIntegration"
        Resource  = aws_redshiftserverless_namespace.aw.arn
      }
    ]
  })
}

resource "aws_redshift_integration" "ddb" {
  for_each         = local.table_arn
  integration_name = "${var.name}-zetl-${replace(each.key, "aw-", "")}"
  source_arn       = each.value
  target_arn       = aws_redshiftserverless_namespace.aw.arn
  depends_on       = [aws_redshift_resource_policy.namespace, aws_dynamodb_resource_policy.zero_etl]
}
