output "vpc_id" {
  value       = module.network.vpc_id
  description = "Created VPC ID"
}

output "vpc_zone" {
  value       = module.network.vpc_zone
  description = "VPC zone (cluster uses this); useful for other resources in the same zone"
}

output "cks_cluster_id" {
  value       = module.cks.cluster_id
  description = "CKS cluster ID"
}

output "cks_cluster_name" {
  value       = module.cks.cluster_name
  description = "CKS cluster name"
}

output "cks_api_server_endpoint" {
  value       = module.cks.api_server_endpoint
  description = "CKS Kubernetes API server endpoint"
}

output "cks_service_account_oidc_issuer_url" {
  value       = module.cks.service_account_oidc_issuer_url
  description = "OIDC issuer URL for service account tokens. Use this as the issuer URL when configuring Workload Identity Federation for Object Storage."
}

output "cks_status" {
  value       = module.cks.status
  description = "CKS cluster status"
}

output "object_storage_bucket_name" {
  value       = module.object_storage.bucket_name
  description = "Created object storage bucket name (null if no bucket created)"
}

output "object_storage_org_access_policy_names" {
  value       = module.object_storage.org_access_policy_names
  description = "Map of created organization access policy names (empty if none created)"
}

output "object_storage_bucket_policy_json" {
  value       = module.object_storage.bucket_policy_json
  description = "Applied bucket policy JSON (null if not created)"
}

output "nodepools" {
  value       = { for k, m in module.nodepool : k => m.nodepool_name }
  description = "Map of created NodePool names: key -> nodepool_name (empty if create_nodepool is false)"
}

output "dfs_pvcs" {
  value       = { for k, m in module.dfs : k => { pvc_name = m.pvc_name, namespace = m.namespace } }
  description = "Map of created DFS PVCs: name -> { pvc_name, namespace } (empty if create_dfs_pvc is false)"
}
