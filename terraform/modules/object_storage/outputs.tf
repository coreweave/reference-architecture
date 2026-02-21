output "bucket_name" {
  value       = length(coreweave_object_storage_bucket.main) > 0 ? coreweave_object_storage_bucket.main[0].name : null
  description = "Created bucket name (null if not created)"
}
