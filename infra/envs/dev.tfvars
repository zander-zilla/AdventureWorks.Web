env    = "dev"
region = "us-east-1"
# Replace with your public IP (curl -s https://checkip.amazonaws.com)/32 before applying.
allowed_cidrs = ["203.0.113.10/32"]
# dev: no SQL Server / DMS (the costliest part); DynamoDB + .NET 10 app + warehouse only.
enable_source            = false
create_dms_service_roles = false
deletion_protection      = false
app_desired_count        = 1
