# One-time, per AWS account, applied from John's machine with admin credentials (local state, kept out of git):
#   - S3 bucket for Terraform remote state (versioned, encrypted, S3-native lock files)
#   - GitHub Actions OIDC provider + roles: no long-lived AWS keys anywhere.
#       aw-github-deploy : assumed only by workflows running in the GitHub environment(s) below (manual dispatch +
#                          optional required reviewers) of zander-zilla/AdventureWorks.Web.
#       aw-github-plan   : read-only + state lock, assumed by pull_request / branch workflows for `terraform plan`.
terraform {
  required_version = ">= 1.11"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}
variable "github_repo" {
  type    = string
  default = "zander-zilla/AdventureWorks.Web"
}
variable "github_environments" {
  description = "GitHub environments whose jobs may assume the deploy role."
  type        = list(string)
  default     = ["demo", "dev"]
}
variable "create_oidc_provider" {
  description = "false if the account already has token.actions.githubusercontent.com"
  type        = bool
  default     = true
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "adventureworks-modernization", ManagedBy = "terraform-bootstrap" } }
}

data "aws_caller_identity" "me" {}
data "aws_partition" "p" {}

locals {
  account  = data.aws_caller_identity.me.account_id
  part     = data.aws_partition.p.partition
  oidc     = "token.actions.githubusercontent.com"
  oidc_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:${local.part}:iam::${local.account}:oidc-provider/${local.oidc}"
}

resource "aws_s3_bucket" "state" {
  bucket = "aw-tfstate-${local.account}-${var.region}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*",
      Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } } }]
  })
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_oidc_provider ? 1 : 0
  url            = "https://${local.oidc}"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "deploy" {
  name                 = "aw-github-deploy"
  max_session_duration = 7200
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "${local.oidc}:aud" = "sts.amazonaws.com" }
        StringLike   = { "${local.oidc}:sub" = [for e in var.github_environments : "repo:${var.github_repo}:environment:${e}"] }
      }
    }]
  })
}

# PowerUserAccess covers every service in the stack except IAM; IAM is limited to the stack's own roles/policies.
resource "aws_iam_role_policy_attachment" "deploy_poweruser" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:${local.part}:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy" "deploy_iam" {
  name = "stack-iam"
  role = aws_iam_role.deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateRole",
        "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy", "iam:ListRolePolicies",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:PassRole"],
        Resource = ["arn:${local.part}:iam::${local.account}:role/aw-*", "arn:${local.part}:iam::${local.account}:role/dms-vpc-role",
      "arn:${local.part}:iam::${local.account}:role/dms-cloudwatch-logs-role"] },
      { Effect = "Allow", Action = ["iam:CreateServiceLinkedRole"], Resource = "*" }
    ]
  })
}

resource "aws_iam_role" "plan" {
  name = "aw-github-plan"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "${local.oidc}:aud" = "sts.amazonaws.com" }
        StringLike   = { "${local.oidc}:sub" = ["repo:${var.github_repo}:pull_request", "repo:${var.github_repo}:ref:refs/heads/*"] }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:${local.part}:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_lock" {
  name = "state-lock"
  role = aws_iam_role.plan.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.state.arn}/*.tflock" }]
  })
}

output "state_bucket" { value = aws_s3_bucket.state.bucket }
output "deploy_role_arn" { value = aws_iam_role.deploy.arn }
output "plan_role_arn" { value = aws_iam_role.plan.arn }
