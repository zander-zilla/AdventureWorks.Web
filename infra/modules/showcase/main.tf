# Phase 8 showcase hosting (ADR 0009): private S3 bucket + CloudFront (origin access control).
# The static build (showcase/build.py) is uploaded by scripts/aws/push-showcase.sh; Terraform only owns the bucket and
# distribution, so content updates never need an apply. Survives app_desired_count = 0; costs ~nothing when idle.
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "price_class" {
  type    = string
  default = "PriceClass_100"
}
variable "force_destroy" {
  description = "Let teardown delete the bucket with its (rebuildable) content."
  type        = bool
  default     = true
}

resource "aws_s3_bucket" "site" {
  bucket_prefix = "${var.name}-showcase-"
  force_destroy = var.force_destroy
}
resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name}-showcase"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# AWS managed policies: CachingOptimized for the site, CachingDisabled for config.json and the replay API.
locals {
  caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  caching_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  security_headers  = "67f7725c-6f97-4210-82d7-5512b31e9d03" # Managed-SecurityHeadersPolicy
  origin_id         = "s3-showcase"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.name} modernization showcase"
  default_root_object = "index.html"
  price_class         = var.price_class
  http_version        = "http2and3"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }
  default_cache_behavior {
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.caching_optimized
    response_headers_policy_id = local.security_headers
  }
  dynamic "ordered_cache_behavior" {
    for_each = ["config.json", "api/*", "data/*"]
    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = local.origin_id
      viewer_protocol_policy     = "redirect-to-https"
      allowed_methods            = ["GET", "HEAD"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = true
      cache_policy_id            = local.caching_disabled
      response_headers_policy_id = local.security_headers
    }
  }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate { cloudfront_default_certificate = true }
}

data "aws_iam_policy_document" "site" {
  statement {
    sid       = "CloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}
resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}

output "bucket" { value = aws_s3_bucket.site.bucket }
output "distribution_id" { value = aws_cloudfront_distribution.site.id }
output "url" { value = "https://${aws_cloudfront_distribution.site.domain_name}/" }
output "origin" { value = "https://${aws_cloudfront_distribution.site.domain_name}" }
