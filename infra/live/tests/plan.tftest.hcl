# Offline plan tests (terraform test + mock providers): no AWS credentials, nothing created. Run in CI (infra workflow).
mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1", name = "us-east-1" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_cloudfront_function" { # C2-1 showcase paths function (distribution validates the ARN)
    defaults = { arn = "arn:aws:cloudfront::123456789012:function/aw-ci-showcase-paths" }
  }
}
mock_provider "random" {}

variables {
  env           = "ci"
  allowed_cidrs = ["203.0.113.10/32"]
}

run "demo_full_stack" {
  command = plan
  variables {
    enable_source = true
  }
  # W-1: AWS-owned keys (SSE disabled) on five tables, CMKs on the two PII tables
  assert {
    condition     = length(module.dynamodb.kms_key_arns) == 2
    error_message = "expected CMKs on aw-customer and aw-hr only"
  }
  assert {
    condition     = length(module.cdc) == 1 && length(module.source_db) == 1
    error_message = "source + CDC expected in the full stack"
  }
  assert {
    condition     = length(module.warehouse.integration_ids) == 7
    error_message = "one zero-ETL integration per domain table"
  }
  assert {
    condition     = length(module.ai) == 0 && length(module.app.ai_policy_count) == 0
    error_message = "C2-5 AI layer must be off by default"
  }
}

run "ai_layer_on" {
  command = plan
  variables {
    enable_ai = true
  }
  assert {
    condition     = length(module.ai) == 1 && length(module.app.ai_policy_count) == 1
    error_message = "enable_ai creates the AI module and the app's AI policy"
  }
  assert {
    condition     = module.ai[0].vector_bucket == "aw-ci-vectors-123456789012"
    error_message = "vector bucket named per account"
  }
}

# C2-6 shop guardrail (John, 2026-10-13): separate from ask-the-data, all six settings.
run "ai_shop_guardrail" {
  command = plan
  module {
    source = "../modules/ai"
  }
  variables {
    name               = "aw-ci"
    redshift_workgroup = "aw-ci"
    competitor_words   = ["RivalBikes"]
  }
  assert {
    condition     = aws_bedrock_guardrail.shop.name == "aw-ci-shop-assistant" && aws_bedrock_guardrail.ask.name == "aw-ci-ask-the-data"
    error_message = "two guardrails: shop and ask-the-data"
  }
  assert {
    condition = alltrue([for f in aws_bedrock_guardrail.shop.content_policy_config[0].filters_config :
    f.type == "PROMPT_ATTACK" ? (f.input_strength == "HIGH" && f.output_strength == "NONE") : (f.input_strength == "HIGH" && f.output_strength == "HIGH")])
    error_message = "content filters HIGH in and out; prompt attack HIGH on input"
  }
  assert {
    condition     = toset([for f in aws_bedrock_guardrail.shop.content_policy_config[0].filters_config : f.type]) == toset(["HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT", "PROMPT_ATTACK"])
    error_message = "five content filters plus prompt attack"
  }
  assert {
    condition     = aws_bedrock_guardrail.shop.word_policy_config[0].managed_word_lists_config[0].type == "PROFANITY" && length(aws_bedrock_guardrail.shop.word_policy_config[0].words_config) == 1
    error_message = "managed profanity list plus the custom word list"
  }
  assert {
    condition     = length(aws_bedrock_guardrail.shop.topic_policy_config[0].topics_config) == 3
    error_message = "three denied topics"
  }
  assert {
    condition = { for p in aws_bedrock_guardrail.shop.sensitive_information_policy_config[0].pii_entities_config : p.type => p.action } == {
    EMAIL = "ANONYMIZE", PHONE = "ANONYMIZE", ADDRESS = "ANONYMIZE", NAME = "ANONYMIZE", CREDIT_DEBIT_CARD_NUMBER = "BLOCK", PASSWORD = "BLOCK" }
    error_message = "PII: anonymize e-mail, phone, address, name; block cards and passwords"
  }
  assert {
    condition     = { for f in aws_bedrock_guardrail.shop.contextual_grounding_policy_config[0].filters_config : f.type => f.threshold } == { GROUNDING = 0.7, RELEVANCE = 0.7 }
    error_message = "contextual grounding 0.7 / relevance 0.7"
  }
  assert {
    condition     = length([for e in output.environment : e if e.name == "Ai__Features__shop__Model" && e.value == "amazon.nova-lite-v1:0"]) == 1
    error_message = "shop chat on Nova Lite"
  }
}

run "dynamodb_encryption_per_table" {
  command = plan
  module {
    source = "../modules/dynamodb"
  }
  variables {
    name       = "aw-ci"
    tables     = { "aw-catalog" = ["GSI1", "GSI2"], "aw-customer" = ["GSI1", "GSI2"], "aw-hr" = ["GSI1", "GSI2"], "aw-reference" = ["GSI1"] }
    cmk_tables = ["aw-customer", "aw-hr"]
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-catalog"].server_side_encryption[0].enabled == false
    error_message = "aw-catalog must use the AWS-owned key (SSE disabled), not the AWS-managed key"
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-hr"].server_side_encryption[0].enabled == true
    error_message = "aw-hr must use its CMK"
  }
  assert {
    condition     = aws_dynamodb_table.t["aw-reference"].point_in_time_recovery[0].enabled
    error_message = "PITR is a zero-ETL prerequisite"
  }
  assert {
    condition     = length(aws_dynamodb_table.t["aw-reference"].global_secondary_index) == 1
    error_message = "aw-reference has GSI1 only"
  }
}

run "dev_without_source_or_quicksight" {
  command = plan
  variables {
    enable_source            = false
    create_dms_service_roles = false
  }
  assert {
    condition     = length(module.cdc) == 0 && length(module.source_db) == 0 && output.before_url == null
    error_message = "enable_source=false must drop RDS/DMS/Kinesis/Lambda and the before app"
  }
}

run "quicksight_toggle" {
  command = plan
  variables {
    enable_source            = false
    enable_quicksight        = true
    quicksight_principal_arn = "arn:aws:quicksight:us-east-1:123456789012:user/default/john"
  }
  assert {
    condition     = module.warehouse.quicksight_enabled
    error_message = "QuickSight data set expected when enable_quicksight = true"
  }
}

run "quicksight_requires_principal" {
  command = plan
  variables {
    enable_quicksight = true
  }
  expect_failures = [var.quicksight_principal_arn]
}

run "budget_alert" {
  command = plan
  variables {
    budget_alert_emails = ["ops@example.com"]
  }
  assert {
    condition     = length(aws_budgets_budget.monthly) == 1 && aws_budgets_budget.monthly[0].limit_amount == "50"
    error_message = "USD 50/month budget expected when an alert e-mail is set"
  }
}

run "no_budget_without_email" {
  command = plan
  assert {
    condition     = length(aws_budgets_budget.monthly) == 0
    error_message = "no budget without alert e-mails"
  }
}

run "showcase_s3_cloudfront" {
  command = plan
  assert {
    condition     = length(module.showcase) == 1
    error_message = "showcase (S3 + CloudFront) expected by default"
  }
}

run "showcase_bucket_private" {
  command = plan
  module {
    source = "../modules/showcase"
  }
  variables {
    name = "aw-ci"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.site.block_public_policy && aws_s3_bucket_public_access_block.site.restrict_public_buckets
    error_message = "showcase bucket must stay private (CloudFront OAC only)"
  }
  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "HTTPS only"
  }
}

run "showcase_off" {
  command = plan
  variables {
    enable_showcase = false
  }
  assert {
    condition     = length(module.showcase) == 0
    error_message = "enable_showcase = false must drop the showcase"
  }
}

# ---------------- Phase 8b ----------------
run "monitor_api_behind_cloudfront" {
  command = plan
  assert {
    condition     = output.showcase_monitor_api && length(module.cdc[0].monitor_api_function) > 0
    error_message = "S-2: monitor API Lambda expected with source + showcase"
  }
}

run "monitor_api_off_without_source" {
  command = plan
  variables {
    enable_source            = false
    create_dms_service_roles = false
  }
  assert {
    condition     = output.showcase_monitor_api == false
    error_message = "no monitor API without the CDC path (the site keeps the recorded replay)"
  }
}

run "showcase_api_failover_to_replay" {
  command = apply # mock provider: sets with computed members are only known after (mock) apply
  module {
    source = "../modules/showcase"
  }
  override_resource {
    target = aws_cloudfront_distribution.site
    values = { arn = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE", domain_name = "d111.cloudfront.net" }
  }
  variables {
    name                 = "aw-ci"
    enable_monitor_api   = true
    monitor_api_url      = "https://abc123.lambda-url.us-east-1.on.aws/"
    monitor_api_function = "aw-ci-monitor-api"
  }
  assert {
    condition     = length(aws_cloudfront_distribution.site.origin_group) == 1 && length(aws_cloudfront_distribution.site.origin) == 2
    error_message = "S-2: /api/* must use an origin group (Lambda first, S3 replay second)"
  }
  assert {
    condition     = contains(one(aws_cloudfront_distribution.site.origin_group).failover_criteria[0].status_codes, 503)
    error_message = "a 503 from the monitor API must fail over to the recorded sample"
  }
  assert {
    condition     = one([for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.target_origin_id if b.path_pattern == "api/*"]) == "api-live-or-replay"
    error_message = "api/* must target the origin group"
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.monitor[0].origin_access_control_origin_type == "lambda"
    error_message = "Function URL must be reached through Lambda origin access control"
  }
  assert {
    condition     = aws_lambda_permission.monitor_url[0].function_url_auth_type == "AWS_IAM"
    error_message = "Function URL invoke permission for CloudFront expected"
  }
}

run "https_with_existing_certificate" {
  command = plan
  variables {
    certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"
    domain_name     = "demo.example.com" # DNS managed elsewhere (no route53_zone_id)
  }
  assert {
    condition     = output.https && length(aws_acm_certificate.alb) == 0
    error_message = "S-3: an existing certificate turns on HTTPS without requesting a new one"
  }
  assert {
    condition     = output.after_url == "https://demo.example.com/" && output.before_url == "https://demo.example.com:8080/" && length(aws_route53_record.alb) == 0
    error_message = "both apps on HTTPS so the HTTPS showcase can frame them"
  }
}

run "https_from_domain_name_with_route53" {
  command = plan
  variables {
    domain_name     = "demo.example.com"
    route53_zone_id = "Z0000000000000000000"
  }
  assert {
    condition     = length(aws_acm_certificate.alb) == 1 && aws_acm_certificate.alb[0].validation_method == "DNS"
    error_message = "S-3: domain_name requests a DNS-validated ACM certificate"
  }
  assert {
    condition     = output.after_url == "https://demo.example.com/" && output.before_url == "https://demo.example.com:8080/"
    error_message = "app URLs use the domain name over HTTPS"
  }
  assert {
    condition     = length(aws_route53_record.alb) == 1
    error_message = "alias record to the ALB expected with route53_zone_id"
  }
}

run "domain_name_validation" {
  command = plan
  variables {
    domain_name = "Not A Domain"
  }
  expect_failures = [var.domain_name]
}

run "http_by_default" {
  command = plan
  assert {
    condition     = !output.https && length(aws_acm_certificate.alb) == 0
    error_message = "HTTP only unless a certificate or domain is configured"
  }
}

run "showcase_chapter1_frozen_prefix" {
  command = apply # C2-1: /c1/ on the same distribution; ordered behaviours are only fully known after (mock) apply
  module {
    source = "../modules/showcase"
  }
  override_resource {
    target = aws_cloudfront_distribution.site
    values = { arn = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE", domain_name = "d111.cloudfront.net" }
  }
  variables {
    name = "aw-ci"
  }
  assert {
    condition     = [for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.path_pattern][0] == "c1/config.json" && [for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.path_pattern][1] == "c1/*"
    error_message = "c1/config.json (no cache) must precede the long-TTL c1/* behaviour"
  }
  assert {
    condition     = one([for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.cache_policy_id if b.path_pattern == "c1/config.json"]) == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    error_message = "c1/config.json carries today's stack URLs and must not be cached"
  }
  assert {
    condition     = aws_cloudfront_cache_policy.frozen.default_ttl >= 86400 && length(aws_cloudfront_distribution.site.origin) == 1
    error_message = "frozen Chapter 1 uses a long TTL on the same S3 origin"
  }
  assert {
    condition     = length(aws_cloudfront_distribution.site.default_cache_behavior[0].function_association) == 1 && aws_cloudfront_function.paths.runtime == "cloudfront-js-2.0"
    error_message = "directory URIs (/c1/) need the viewer-request index rewrite"
  }
  assert {
    condition     = output.chapter1_url == "https://d111.cloudfront.net/c1/"
    error_message = "chapter1_url output"
  }
}

run "ai_watchdog_monitor_api" {
  command = plan
  module {
    source = "../modules/ai"
  }
  variables {
    name                     = "aw-ci"
    redshift_workgroup       = "aw-ci"
    monitor_api_url          = "https://abc.lambda-url.us-east-1.on.aws/"
    monitor_api_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:aw-ci-monitor-api"
  }
  assert {
    condition     = one([for e in output.environment : e.value if e.name == "Ai__MonitorApiUrl"]) == "https://abc.lambda-url.us-east-1.on.aws/" && one([for e in output.environment : e.value if e.name == "Ai__MonitorSigV4"]) == "true"
    error_message = "the app gets the monitor API URL and signs its calls"
  }
  assert {
    condition     = strcontains(output.monitor_policy_json, "lambda:InvokeFunctionUrl") && strcontains(output.monitor_policy_json, "aw-ci-monitor-api") && strcontains(output.monitor_policy_json, "AWS_IAM")
    error_message = "invoke permission on the monitor API Function URL only"
  }
}

run "ai_watchdog_without_monitor_api" {
  command = plan
  module {
    source = "../modules/ai"
  }
  variables {
    name               = "aw-ci"
    redshift_workgroup = "aw-ci"
  }
  assert {
    condition     = output.monitor_policy_json == "[]" && length([for e in output.environment : e if e.name == "Ai__MonitorApiUrl"]) == 0
    error_message = "no monitor API: recorded scenarios, no Lambda permission"
  }
}
