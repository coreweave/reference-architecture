# CoreWeave AI Object Storage bucket (S3-compatible).
# Required: user must be in an S3 policy that allows ListBuckets, CreateBucket (see README).
resource "coreweave_object_storage_bucket" "main" {
  count  = var.bucket_name != null ? 1 : 0
  name   = var.bucket_name
  zone   = var.zone
  tags   = var.tags
}

# --- Organization access policies ---
# Enforce permissions across your entire CoreWeave organization.
# At least one org access policy must exist before you can create a bucket.
# Use the map to create multiple policies (e.g. one for humans, one for OIDC roles).
resource "coreweave_object_storage_organization_access_policy" "main" {
  for_each = var.org_access_policies

  name       = each.key
  statements = each.value.statements
}

# --- Bucket access policy (optional, per-bucket) ---
# Evaluated after organization access policies. Uses the policy document data source for type safety.
data "coreweave_object_storage_bucket_policy_document" "main" {
  count = var.bucket_name != null && var.bucket_policy_statements != null ? 1 : 0

  version = "2012-10-17"

  dynamic "statement" {
    for_each = var.bucket_policy_statements
    content {
      sid       = statement.value.sid
      effect    = statement.value.effect
      action    = statement.value.actions
      resource  = statement.value.resources
      principal = statement.value.principals
    }
  }
}

resource "coreweave_object_storage_bucket_policy" "main" {
  count = var.bucket_name != null && var.bucket_policy_statements != null ? 1 : 0

  bucket = coreweave_object_storage_bucket.main[0].name
  policy = data.coreweave_object_storage_bucket_policy_document.main[0].json
}
