# One-time static carry-over (decision 3): CSVs from warehouse/local/static_export.py --out -> s3://<bucket>/static/ -> COPY
resource "aws_s3_bucket" "static" {
  bucket_prefix = "${var.name}-dw-static-"
}
resource "aws_s3_bucket_public_access_block" "static" {
  bucket                  = aws_s3_bucket.static.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "static" {
  bucket = aws_s3_bucket.static.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.warehouse.arn
    }
  }
}
resource "aws_s3_bucket_versioning" "static" {
  bucket = aws_s3_bucket.static.id
  versioning_configuration { status = "Enabled" }
}
