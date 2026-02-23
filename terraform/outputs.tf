output "vpc_id" {
  value       = module.network.vpc_id
  description = "Created VPC ID"
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
  description = "OIDC issuer URL for service account tokens"
}

output "cks_status" {
  value       = module.cks.status
  description = "CKS cluster status"
}

output "object_storage_bucket_name" {
  value       = module.object_storage.bucket_name
  description = "Created object storage bucket name (null if no bucket created)"
}

output "nodepools" {
  value       = { for k, m in module.nodepool : k => m.nodepool_name }
  description = "Map of created NodePool names: key -> nodepool_name (empty if create_nodepool is false)"
}

output "dfs_pvcs" {
  value       = { for k, m in module.dfs : k => { pvc_name = m.pvc_name, namespace = m.namespace } }
  description = "Map of created DFS PVCs: name -> { pvc_name, namespace } (empty if create_dfs_pvc is false)"
}
