# CoreWeave AI Object Storage bucket (S3-compatible).
# Required: user must be in an S3 policy that allows ListBuckets, CreateBucket (see README).
resource "coreweave_object_storage_bucket" "main" {
  count  = var.bucket_name != null ? 1 : 0
  name   = var.bucket_name
  zone   = var.zone
  tags   = var.tags
}
