# Phase 8b (S-3): HTTPS on the ALB. Either bring an ACM certificate (certificate_arn) or set domain_name and let
# Terraform request one (DNS validation). With route53_zone_id the validation records and an alias to the ALB are
# created here; without it, add the CNAMEs from output certificate_validation_records at your DNS provider while the
# apply waits (aws_acm_certificate_validation, up to 75 min) and point domain_name at output alb_dns.
locals {
  create_certificate = var.certificate_arn == "" && var.domain_name != ""
  https              = var.certificate_arn != "" || var.domain_name != ""
  certificate_arn    = var.certificate_arn != "" ? var.certificate_arn : (local.create_certificate ? aws_acm_certificate_validation.alb[0].certificate_arn : "")
}

resource "aws_acm_certificate" "alb" {
  count             = local.create_certificate ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"
  lifecycle { create_before_destroy = true }
}

# One name on the certificate -> one validation record (count, so the plan does not depend on computed set keys).
resource "aws_route53_record" "certificate_validation" {
  count           = local.create_certificate && var.route53_zone_id != "" ? 1 : 0
  zone_id         = var.route53_zone_id
  name            = one(aws_acm_certificate.alb[0].domain_validation_options).resource_record_name
  type            = one(aws_acm_certificate.alb[0].domain_validation_options).resource_record_type
  records         = [one(aws_acm_certificate.alb[0].domain_validation_options).resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "alb" {
  count                   = local.create_certificate ? 1 : 0
  certificate_arn         = aws_acm_certificate.alb[0].arn
  validation_record_fqdns = var.route53_zone_id != "" ? aws_route53_record.certificate_validation[*].fqdn : null
}

resource "aws_route53_record" "alb" {
  count   = var.domain_name != "" && var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = module.app.alb_dns
    zone_id                = module.app.alb_zone_id
    evaluate_target_health = false
  }
}

output "alb_dns" { value = module.app.alb_dns }
output "https" { value = local.https }
output "certificate_validation_records" {
  description = "CNAMEs to create at your DNS provider when route53_zone_id is empty."
  value = local.create_certificate ? [for o in aws_acm_certificate.alb[0].domain_validation_options : {
    name = o.resource_record_name, type = o.resource_record_type, value = o.resource_record_value
  }] : []
}
