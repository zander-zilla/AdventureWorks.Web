locals {
  account   = data.aws_caller_identity.me.account_id
  part      = data.aws_partition.p.partition
  region    = data.aws_region.r.region
  table_arn = var.dynamodb_table_arns
}

resource "aws_kms_key" "warehouse" {
  description         = "${var.name} Redshift Serverless namespace + static-data bucket"
  enable_key_rotation = true
}

resource "aws_iam_role" "redshift" {
  name = "${var.name}-redshift-serverless"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"] }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "redshift_static_copy" {
  name = "static-copy"
  role = aws_iam_role.redshift.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket"], Resource = [aws_s3_bucket.static.arn, "${aws_s3_bucket.static.arn}/static/*"] },
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = [aws_kms_key.warehouse.arn] }
    ]
  })
}

resource "aws_redshiftserverless_namespace" "aw" {
  namespace_name        = "${var.name}-analytics"
  db_name               = "aw_dw"
  kms_key_id            = aws_kms_key.warehouse.arn
  iam_roles             = [aws_iam_role.redshift.arn]
  default_iam_role_arn  = aws_iam_role.redshift.arn
  manage_admin_password = true
  log_exports           = ["userlog", "connectionlog", "useractivitylog"]
}

resource "aws_redshiftserverless_workgroup" "aw" {
  workgroup_name       = "${var.name}-analytics"
  namespace_name       = aws_redshiftserverless_namespace.aw.namespace_name
  base_capacity        = var.base_capacity_rpu
  max_capacity         = var.max_capacity_rpu
  publicly_accessible  = false
  enhanced_vpc_routing = true
  subnet_ids           = var.subnet_ids
  security_group_ids   = var.security_group_ids

  # required by zero-ETL integrations (DynamoDB attribute names are case sensitive)
  config_parameter {
    parameter_key   = "enable_case_sensitive_identifier"
    parameter_value = "true"
  }
}

# Cap spend: stop queries once the monthly RPU-hour budget is used.
resource "aws_redshiftserverless_usage_limit" "monthly" {
  resource_arn  = aws_redshiftserverless_workgroup.aw.arn
  usage_type    = "serverless-compute"
  amount        = var.monthly_rpu_hours_limit
  period        = "monthly"
  breach_action = "deactivate"
}
