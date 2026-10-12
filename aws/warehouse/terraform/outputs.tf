output "workgroup" { value = aws_redshiftserverless_workgroup.aw.workgroup_name }
output "static_bucket" { value = aws_s3_bucket.static.bucket }
output "copy_role_arn" { value = aws_iam_role.redshift.arn }
output "integration_arns" { value = { for k, v in aws_redshift_integration.ddb : k => v.arn } }
output "quicksight_data_set_arn" { value = local.qs ? aws_quicksight_data_set.sales[0].arn : null }
