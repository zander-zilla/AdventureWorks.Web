# Phase 7 decision 5 (John): AWS Budgets alert, ~USD 50/month. The demo is torn down after each use, so a
# breach means something was left running (most likely RDS SQL Server SE). Account-wide on purpose: leftovers
# outside the aw-* tags are what we want to catch.
resource "aws_budgets_budget" "monthly" {
  count        = length(var.budget_alert_emails) > 0 ? 1 : 0
  name         = "aw-${var.env}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_monthly_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_alert_emails
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_alert_emails
  }
}
