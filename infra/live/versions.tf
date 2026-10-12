terraform {
  required_version = ">= 1.11"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Partial config: `terraform init -backend-config=../envs/<env>.s3.tfbackend` (bucket from infra/bootstrap).
  # S3-native locking (use_lockfile) - no DynamoDB lock table.
  backend "s3" {}
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "adventureworks-modernization"
      Environment = var.env
      ManagedBy   = "terraform"
      Owner       = var.owner
    }
  }
}
