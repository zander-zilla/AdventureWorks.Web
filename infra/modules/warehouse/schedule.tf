# Scheduled star-schema rebuild: EventBridge Scheduler -> Redshift Data API -> CALL dw.sp_build_star()
resource "aws_iam_role" "scheduler" {
  name = "${var.name}-star-build-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = { StringEquals = { "aws:SourceAccount" = local.account } } }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "redshift-data"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["redshift-data:ExecuteStatement"], Resource = aws_redshiftserverless_workgroup.aw.arn },
      { Effect = "Allow", Action = ["redshift-serverless:GetCredentials"], Resource = aws_redshiftserverless_workgroup.aw.arn }
    ]
  })
}

resource "aws_scheduler_schedule" "star_build" {
  name                = "${var.name}-star-build"
  schedule_expression = var.build_schedule
  flexible_time_window { mode = "OFF" }
  target {
    arn      = "arn:${local.part}:scheduler:::aws-sdk:redshiftdata:executeStatement"
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      WorkgroupName = aws_redshiftserverless_workgroup.aw.workgroup_name
      Database      = "aw_dw"
      Sql           = "CALL dw.sp_build_star()"
      StatementName = "aw-star-build"
      WithEvent     = true
    })
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
