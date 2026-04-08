output "kms_crypto_key_id" {
  description = "Cloud KMS key identifier used for secret encryption."
  value       = google_kms_crypto_key.secrets.id
}

output "effective_cks_oidc_issuer_url" {
  description = "Effective CKS OIDC issuer URL used for Workload Identity Federation."
  value       = local.effective_cks_oidc_issuer_url
}

output "workload_identity_pool_id" {
  description = "Effective Workload Identity Pool ID used for Secret Manager access."
  value       = local.effective_workload_identity_pool_id
}

output "workload_identity_provider_name" {
  description = "Created Workload Identity Provider resource name (null when create_workload_identity_pool=false)."
  value       = try(google_iam_workload_identity_pool_provider.cks_oidc[0].name, null)
}

output "secret_names" {
  description = "Secret Manager secret names referenced by manifests/30-external-secret.yaml."
  value       = local.secret_names
}

output "workload_identity_principal" {
  description = "Workload Identity principal granted Secret Manager access."
  value       = "principal://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${local.effective_workload_identity_pool_id}/subject/${local.effective_wif_subject}"
}

output "namespace" {
  description = "Kubernetes namespace expected by the default workload identity subject."
  value       = var.namespace
}

output "service_account_name" {
  description = "Kubernetes service account expected by the default workload identity subject."
  value       = var.service_account_name
}
