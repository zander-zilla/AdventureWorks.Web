variable "env" {
  description = "Environment name (demo, dev, ...). One environment per account+region: the DynamoDB table names (aw-*) are fixed by the mapping."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,9}$", var.env))
    error_message = "env: 2-10 lowercase letters/digits."
  }
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "owner" {
  type    = string
  default = "john.vandervliet"
}
variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}
variable "allowed_cidrs" {
  description = "Who may reach the ALB (set to your own IP/32 for demos)."
  type        = list(string)
}
variable "certificate_arn" {
  description = "Optional existing ACM certificate (same region as the ALB) for HTTPS on the ALB. Takes precedence over domain_name's generated certificate."
  type        = string
  default     = ""
}
variable "domain_name" {
  description = "Phase 8b (S-3): public host name for the apps, e.g. demo.example.com. With certificate_arn empty, Terraform requests an ACM certificate for it (DNS validation) and turns on HTTPS on the ALB (443 After App, 8080 Before App)."
  type        = string
  default     = ""
  validation {
    condition     = var.domain_name == "" || can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", var.domain_name))
    error_message = "domain_name: a lowercase DNS name such as demo.example.com."
  }
}
variable "route53_zone_id" {
  description = "Optional Route 53 hosted zone of domain_name: creates the ACM validation records and an alias record to the ALB. Empty = add the records shown in output certificate_validation_records at your DNS provider."
  type        = string
  default     = ""
}

# --- source (before) ---
variable "sql_instance_class" {
  description = "RDS SQL Server SE instance class (license included)."
  type        = string
  default     = "db.m6i.large"
}
variable "enable_source" {
  description = "RDS SQL Server + DMS + Kinesis + Lambda CDC path (the costliest part). false = DynamoDB + app + warehouse only."
  type        = bool
  default     = true
}
variable "enable_before_app" {
  description = "Host the original app (on SQL Server) for the live CDC demo. Requires enable_source."
  type        = bool
  default     = true
}

# --- CDC ---
variable "dms_instance_class" {
  type    = string
  default = "dms.t3.medium"
}
variable "kinesis_shards" {
  type    = number
  default = 1
}
variable "lambda_zip" {
  description = "Path of the CDC Lambda package built by cdc/lambda/build.sh."
  type        = string
  default     = "../../dist/aw-cdc-lambda.zip"
}
variable "monitor_api_zip" {
  description = "Path of the replication monitor API Lambda package (cdc/lambda/build.sh)."
  type        = string
  default     = "../../dist/aw-monitor-api.zip"
}
variable "create_dms_service_roles" {
  type    = bool
  default = true
}

# --- DynamoDB ---
variable "cmk_tables" {
  description = "Decision W-1: customer-managed keys only on the PII tables; AWS-owned keys elsewhere."
  type        = list(string)
  default     = ["aw-customer", "aw-hr"]
}
variable "deletion_protection" {
  description = "DynamoDB deletion protection (mapping.yaml table_settings). scripts/aws/teardown.sh turns it off before destroy."
  type        = bool
  default     = true
}

# --- app ---
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "app_desired_count" {
  description = "0 pauses the Fargate services (ALB keeps billing)."
  type        = number
  default     = 1
}

# --- warehouse ---
variable "redshift_base_rpu" {
  type    = number
  default = 8
}
variable "redshift_max_rpu" {
  type    = number
  default = 32
}
variable "redshift_monthly_rpu_hours_limit" {
  type    = number
  default = 200
}
variable "star_build_schedule" {
  description = "Decision W-2: hourly."
  type        = string
  default     = "rate(1 hour)"
}
variable "enable_quicksight" {
  description = "Decision W-4: QuickSight only for the showcase (needs a QuickSight Enterprise subscription first)."
  type        = bool
  default     = false
}
variable "quicksight_principal_arn" {
  description = "QuickSight user/group ARN; required when enable_quicksight = true."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_quicksight || var.quicksight_principal_arn != ""
    error_message = "quicksight_principal_arn is required when enable_quicksight = true."
  }
}

# --- cost guardrail (Phase 7 decision 5) ---
variable "budget_monthly_usd" {
  description = "AWS Budgets monthly cost limit (USD) for this account; alerts at 80% actual and 100% forecast."
  type        = number
  default     = 50
}
variable "budget_alert_emails" {
  description = "E-mail addresses notified by the AWS Budgets alert. Empty = no budget created."
  type        = list(string)
  default     = []
}

# --- showcase (Phase 8) ---
variable "enable_showcase" {
  description = "Showcase website on S3 + CloudFront (ADR 0009)."
  type        = bool
  default     = true
}
variable "enable_monitor_api" {
  description = "Phase 8b (S-2): Live Replication tab streams real CDC data via a small Lambda behind the showcase CloudFront (falls back to the recorded sample). Needs enable_source and enable_showcase."
  type        = bool
  default     = true
}

variable "enable_ai" {
  description = "C2-5: Bedrock AI layer (semantic search on S3 Vectors, ask-the-data with a guardrail). Off by default."
  type        = bool
  default     = false
}
