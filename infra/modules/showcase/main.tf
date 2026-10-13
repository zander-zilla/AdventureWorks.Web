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
variable "enable_monitor_api" {
  description = "Route /api/* to the replication monitor API Lambda (Phase 8b, S-2), failing over to the recorded replay in S3."
  type        = bool
  default     = false
}
variable "monitor_api_url" {
  description = "Function URL of the monitor API Lambda (modules/cdc output monitor_api_url)."
  type        = string
  default     = ""
}
variable "monitor_api_function" {
  description = "Function name of the monitor API Lambda (for the CloudFront invoke permission)."
  type        = string
  default     = ""
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
  caching_optimized  = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  caching_disabled   = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  security_headers   = "67f7725c-6f97-4210-82d7-5512b31e9d03" # Managed-SecurityHeadersPolicy
  origin_id          = "s3-showcase"
  all_viewer_no_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac" # Managed-AllViewerExceptHostHeader (query string to the Function URL)
  monitor_origin_id  = "lambda-monitor-api"
  api_group_id       = "api-live-or-replay"
  monitor_domain     = replace(trimsuffix(var.monitor_api_url, "/"), "https://", "")
}

# C2-1: long TTL for the frozen Chapter 1 (/c1/*): 30 days default, 1 year max.
resource "aws_cloudfront_cache_policy" "frozen" {
  name        = "${var.name}-showcase-frozen"
  comment     = "Frozen Chapter 1 showcase (C2-1)"
  default_ttl = 2592000
  max_ttl     = 31536000
  min_ttl     = 0
  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
  }
}

# Phase 8b (S-2): CloudFront signs requests to the AWS_IAM Function URL (origin access control for Lambda).
resource "aws_cloudfront_origin_access_control" "monitor" {
  count                             = var.enable_monitor_api ? 1 : 0
  name                              = "${var.name}-monitor-api"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# C2-1: Chapter 1 is frozen under /c1/ (same bucket + distribution). S3 (OAC, REST endpoint) has no index documents
# below the root, so this viewer-request function maps directory URIs to index.html and the short chapter URLs
# (/c1 -> /c1/, /c2[/] -> /#/c2/story; Chapter 2 is a hash-routed SPA at /).
resource "aws_cloudfront_function" "paths" {
  name    = "${var.name}-showcase-paths"
  runtime = "cloudfront-js-2.0"
  comment = "Showcase chapter paths (C2-1)"
  publish = true
  code    = file("${path.module}/paths.js")
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
  dynamic "origin" {
    for_each = var.enable_monitor_api ? [1] : []
    content {
      domain_name              = local.monitor_domain
      origin_id                = local.monitor_origin_id
      origin_access_control_id = aws_cloudfront_origin_access_control.monitor[0].id
      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }
  # Live first, recorded sample second: any 5xx/403/404 from the monitor API (stack paused or torn down, CDC not
  # started, throttled) makes CloudFront answer /api/* from the replay files in the bucket.
  dynamic "origin_group" {
    for_each = var.enable_monitor_api ? [1] : []
    content {
      origin_id = local.api_group_id
      failover_criteria { status_codes = [403, 404, 500, 502, 503, 504] }
      member { origin_id = local.monitor_origin_id }
      member { origin_id = local.origin_id }
    }
  }
  default_cache_behavior {
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.caching_optimized
    response_headers_policy_id = local.security_headers
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.paths.arn
    }
  }
  # C2-1 frozen Chapter 1: c1/config.json carries today's stack URLs (never cached); everything else under /c1/ is
  # immutable (only showcase-freeze.yml / push-showcase-c1.sh write it, with an explicit /c1/* invalidation).
  ordered_cache_behavior {
    path_pattern               = "c1/config.json"
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.caching_disabled
    response_headers_policy_id = local.security_headers
  }
  ordered_cache_behavior {
    path_pattern               = "c1/*"
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.frozen.id
    response_headers_policy_id = local.security_headers
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.paths.arn
    }
  }
  dynamic "ordered_cache_behavior" {
    for_each = var.enable_monitor_api ? ["api/*"] : []
    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = local.api_group_id
      viewer_protocol_policy     = "redirect-to-https"
      allowed_methods            = ["GET", "HEAD"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = true
      cache_policy_id            = local.caching_disabled
      origin_request_policy_id   = local.all_viewer_no_host
      response_headers_policy_id = local.security_headers
    }
  }
  dynamic "ordered_cache_behavior" {
    for_each = var.enable_monitor_api ? ["config.json", "data/*"] : ["config.json", "api/*", "data/*"]
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

# The distribution may invoke the Function URL (both permissions are required for Lambda origin access control).
resource "aws_lambda_permission" "monitor_url" {
  count                  = var.enable_monitor_api ? 1 : 0
  statement_id           = "AllowShowcaseCloudFrontUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = var.monitor_api_function
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.site.arn
  function_url_auth_type = "AWS_IAM"
}
resource "aws_lambda_permission" "monitor_invoke" {
  count         = var.enable_monitor_api ? 1 : 0
  statement_id  = "AllowShowcaseCloudFrontInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.monitor_api_function
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.site.arn
}

output "monitor_api" { value = var.enable_monitor_api }
output "bucket" { value = aws_s3_bucket.site.bucket }
output "distribution_id" { value = aws_cloudfront_distribution.site.id }
output "chapter1_url" { value = "https://${aws_cloudfront_distribution.site.domain_name}/c1/" }
output "url" { value = "https://${aws_cloudfront_distribution.site.domain_name}/" }
output "origin" { value = "https://${aws_cloudfront_distribution.site.domain_name}" }
