env    = "demo"
region = "us-east-1"
# Replace with your public IP (curl -s https://checkip.amazonaws.com)/32 before applying.
allowed_cidrs = ["203.0.113.10/32"]
# demo: the full story (before app -> SQL Server CDC -> DMS -> Kinesis -> Lambda -> DynamoDB -> zero-ETL -> Redshift).
enable_source     = true
enable_before_app = true
enable_quicksight = false # W-4: true only for the showcase, with quicksight_principal_arn
# Phase 7 decision 5: budget alert (set your e-mail before applying).
budget_monthly_usd  = 50
budget_alert_emails = ["john.vandervliet@example.com"]
