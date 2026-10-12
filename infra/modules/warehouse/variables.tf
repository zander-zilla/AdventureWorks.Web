variable "name" {
  description = "Resource name prefix (e.g. aw-demo)."
  type        = string
}
variable "dynamodb_table_arns" {
  description = "Domain tables replicated by zero-ETL (one integration each), table name => ARN. PITR on; AWS-owned or customer-managed key."
  type        = map(string)
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
variable "monthly_rpu_hours_limit" {
  description = "Usage limit: queries are deactivated once this many RPU-hours are used in a month (spend cap)."
  type        = number
  default     = 200
}
variable "build_schedule" {
  description = "When dw.sp_build_star() runs (decision W-2: hourly). Zero-ETL lands DynamoDB changes every 15-30 min."
  type        = string
  default     = "rate(1 hour)"
}
variable "subnet_ids" {
  description = "Redshift Serverless needs subnets in at least three AZs."
  type        = list(string)
}
variable "security_group_ids" {
  type = list(string)
}
variable "enable_quicksight" {
  description = "Decision W-4: QuickSight (Enterprise subscription, billed) only for the showcase."
  type        = bool
  default     = false
}
variable "quicksight_principal_arn" {
  description = "QuickSight user/group ARN granted on the data source/data set. Required when enable_quicksight = true."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_quicksight || var.quicksight_principal_arn != ""
    error_message = "quicksight_principal_arn is required when enable_quicksight = true."
  }
}
variable "quicksight_vpc_connection_arn" {
  type    = string
  default = ""
}
