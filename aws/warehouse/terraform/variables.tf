variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "aw"
}
variable "dynamodb_tables" {
  description = "Domain tables replicated by zero-ETL (one integration each). Created by the phase 3/4 stack (Terraform in phase 7); PITR must be on."
  type        = list(string)
  default     = ["aw-catalog", "aw-customer", "aw-hr", "aw-inventory", "aw-purchasing", "aw-reference", "aw-sales"]
}
variable "base_capacity_rpu" {
  description = "Redshift Serverless base RPUs (8 = minimum; billed per second only while queries/ingestion run)."
  type        = number
  default     = 8
}
variable "max_capacity_rpu" {
  type    = number
  default = 32
}
variable "build_schedule" {
  description = "When dw.sp_build_star() runs. Zero-ETL lands DynamoDB changes every 15-30 min, so hourly is the useful floor."
  type        = string
  default     = "rate(1 hour)"
}
variable "subnet_ids" {
  type    = list(string)
  default = []
}
variable "security_group_ids" {
  type    = list(string)
  default = []
}
variable "quicksight_principal_arn" {
  description = "QuickSight user/group ARN that owns the data source, data set and dashboard."
  type        = string
  default     = ""
}
variable "quicksight_vpc_connection_arn" {
  type    = string
  default = ""
}
