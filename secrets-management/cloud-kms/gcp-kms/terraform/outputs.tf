output "kms_crypto_key_id" {
  description = "Cloud KMS key identifier used for secret encryption."
  value       = google_kms_crypto_key.secrets.id
}

output "secret_names" {
  description = "Secret Manager secret names referenced by manifests/30-external-secret.yaml."
  value       = local.secret_names
}

output "workload_identity_principal" {
  description = "Workload Identity principal granted Secret Manager access."
  value       = "principal://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${var.workload_identity_pool_id}/subject/${local.effective_wif_subject}"
}

output "namespace" {
  description = "Kubernetes namespace expected by the default workload identity subject."
  value       = var.namespace
}

output "service_account_name" {
  description = "Kubernetes service account expected by the default workload identity subject."
  value       = var.service_account_name
}
