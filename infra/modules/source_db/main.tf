# The "before" source: RDS for SQL Server 2022 Standard Edition (CDC needs Standard/Enterprise; Express/Web cannot run
# SQL Server Agent CDC jobs on RDS). AdventureWorks2022 is restored with RDS native restore (SQLSERVER_BACKUP_RESTORE
# option) from the .bak in the backups bucket; CDC is enabled by scripts/aws/db_init.py (msdb.dbo.rds_cdc_enable_db +
# sys.sp_cdc_enable_table for the 68 tables + 7-day retention, P4-4), run as a one-off ECS task inside the VPC.
terraform {
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "vpc_cidr" { type = string }
variable "subnet_ids" { type = list(string) }
variable "instance_class" { type = string }
variable "allocated_storage_gb" {
  type    = number
  default = 20
}
variable "multi_az" {
  type    = bool
  default = false
}
variable "deletion_protection" {
  type    = bool
  default = false
}
variable "skip_final_snapshot" {
  description = "Demo default true: teardown leaves nothing billable behind."
  type        = bool
  default     = true
}

resource "random_password" "master" {
  length           = 24
  special          = true
  override_special = "!#%^*-_=+"
}

# Single secret the ECS tools task (db init, bulk load) reads; DMS gets the password directly (stored in the encrypted
# remote state only).
resource "aws_secretsmanager_secret" "master" {
  name_prefix             = "${var.name}-sqlserver-"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = "awadmin"
    password = random_password.master.result
    host     = aws_db_instance.sql.address
    port     = 1433
  })
}

resource "aws_s3_bucket" "backups" {
  bucket_prefix = "${var.name}-sql-backups-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role" "restore" {
  name = "${var.name}-rds-native-restore"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "rds.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "restore" {
  name = "read-backups"
  role = aws_iam_role.restore.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = aws_s3_bucket.backups.arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectAttributes"], Resource = "${aws_s3_bucket.backups.arn}/*" }
    ]
  })
}

resource "aws_db_option_group" "sql" {
  name                     = "${var.name}-sqlserver-se-16"
  option_group_description = "Native backup/restore for the AdventureWorks2022 .bak"
  engine_name              = "sqlserver-se"
  major_engine_version     = "16.00"
  option {
    option_name = "SQLSERVER_BACKUP_RESTORE"
    option_settings {
      name  = "IAM_ROLE_ARN"
      value = aws_iam_role.restore.arn
    }
  }
}

resource "aws_db_subnet_group" "sql" {
  name       = "${var.name}-sqlserver"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "sql" {
  name        = "${var.name}-sqlserver"
  description = "SQL Server from inside the VPC (DMS, tools task, before app)"
  vpc_id      = var.vpc_id
  ingress {
    from_port   = 1433
    to_port     = 1433
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "sql" {
  identifier             = "${var.name}-sqlserver"
  engine                 = "sqlserver-se"
  engine_version         = "16.00"
  license_model          = "license-included"
  instance_class         = var.instance_class
  allocated_storage      = var.allocated_storage_gb
  storage_type           = "gp3"
  storage_encrypted      = true
  username               = "awadmin"
  password               = random_password.master.result
  db_subnet_group_name   = aws_db_subnet_group.sql.name
  vpc_security_group_ids = [aws_security_group.sql.id]
  option_group_name      = aws_db_option_group.sql.name
  multi_az               = var.multi_az
  publicly_accessible    = false
  # Backups on => FULL recovery model, which DMS CDC requires. 1 day keeps snapshot storage minimal.
  backup_retention_period    = 1
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = var.skip_final_snapshot
  final_snapshot_identifier  = var.skip_final_snapshot ? null : "${var.name}-sqlserver-final"
  auto_minor_version_upgrade = true
  apply_immediately          = true
}

output "address" { value = aws_db_instance.sql.address }
output "port" { value = aws_db_instance.sql.port }
output "username" { value = aws_db_instance.sql.username }
output "password" {
  value     = random_password.master.result
  sensitive = true
}
output "secret_arn" { value = aws_secretsmanager_secret.master.arn }
output "security_group_id" { value = aws_security_group.sql.id }
output "backups_bucket" { value = aws_s3_bucket.backups.bucket }
