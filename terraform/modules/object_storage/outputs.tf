output "bucket_name" {
  value       = length(coreweave_object_storage_bucket.main) > 0 ? coreweave_object_storage_bucket.main[0].name : null
  description = "Created bucket name (null if not created)"
}

output "org_access_policy_names" {
  value       = { for k, v in coreweave_object_storage_organization_access_policy.main : k => v.name }
  description = "Map of created organization access policy names (empty if none created)"
}

output "bucket_policy_json" {
  value       = length(data.coreweave_object_storage_bucket_policy_document.main) > 0 ? data.coreweave_object_storage_bucket_policy_document.main[0].json : null
  description = "Applied bucket policy JSON (null if not created)"
}
