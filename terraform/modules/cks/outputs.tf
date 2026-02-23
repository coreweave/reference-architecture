output "cluster_id" {
  value       = coreweave_cks_cluster.main.id
  description = "CKS cluster ID"
}

output "cluster_name" {
  value       = coreweave_cks_cluster.main.name
  description = "CKS cluster name"
}

output "api_server_endpoint" {
  value       = coreweave_cks_cluster.main.api_server_endpoint
  description = "Kubernetes API server endpoint"
}

output "service_account_oidc_issuer_url" {
  value       = coreweave_cks_cluster.main.service_account_oidc_issuer_url
  description = "OIDC issuer URL for service account tokens"
}

output "status" {
  value       = coreweave_cks_cluster.main.status
  description = "Current cluster status"
}
