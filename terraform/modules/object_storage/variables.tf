variable "bucket_name" {
  type        = string
  description = "Object storage bucket name (globally unique; must not start with cw- or vip-). Set to null to skip creation."
  default     = null
}

variable "zone" {
  type        = string
  description = "Zone for the bucket (e.g. US-EAST-02A)"
}

variable "tags" {
  type        = map(string)
  description = "Tags to assign to the bucket"
  default     = {}
}

# --- Organization access policies ---
variable "org_access_policies" {
  type = map(object({
    statements = set(object({
      name       = string
      effect     = string
      actions    = set(string)
      resources  = set(string)
      principals = set(string)
    }))
  }))
  description = <<-EOT
    Map of organization-wide access policies for Object Storage. Map key = policy name.
    At least one must exist before creating a bucket.
    Each statement needs: name, effect (Allow/Deny), actions (s3:* or cwobject:*), resources, and principals.
    Principals use short-form identifiers (not full ARNs). For OIDC WIF roles: role/<ISSUER_URL>:<SUBJECT>
    Leave empty ({}) to skip.
  EOT
  default     = {}
}

# --- Bucket access policy ---
variable "bucket_policy_statements" {
  type = list(object({
    sid        = string
    effect     = string
    actions    = list(string)
    resources  = list(string)
    principals = map(list(string))
  }))
  description = <<-EOT
    Optional per-bucket access policy statements. Evaluated after organization access policies.
    Each statement needs: sid, effect (Allow/Deny), actions (e.g. ["s3:GetObject"]),
    resources (ARN format, e.g. ["arn:aws:s3:::my-bucket/*"]),
    principals (e.g. { "CW" = ["*"] } or { "CW" = ["arn:aws:iam::<org-id>:role/..."] }).
    Set to null to skip.
  EOT
  default     = null
}
