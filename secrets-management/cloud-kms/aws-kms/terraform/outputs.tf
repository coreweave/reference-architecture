output "vpc_id" {
  description = "CoreWeave VPC ID created for this example."
  value       = module.network.vpc_id
}

output "cks_cluster_id" {
  description = "CKS cluster ID created for this example."
  value       = module.cks.cluster_id
}

output "cks_cluster_name" {
  description = "CKS cluster name created for this example."
  value       = module.cks.cluster_name
}

output "cks_api_server_endpoint" {
  description = "CKS Kubernetes API server endpoint."
  value       = module.cks.api_server_endpoint
}

output "cks_status" {
  description = "Current CKS cluster status."
  value       = module.cks.status
}

output "cks_service_account_oidc_issuer_url" {
  description = "CKS service-account OIDC issuer URL trusted by AWS IAM."
  value       = module.cks.service_account_oidc_issuer_url
}

output "eso_role_arn" {
  description = "IAM role ARN to place in manifests/20-secret-store.yaml."
  value       = aws_iam_role.eso_reader.arn
}

output "effective_oidc_issuer_url" {
  description = "Effective CKS OIDC issuer URL used by this stack."
  value       = local.effective_oidc_issuer_url
}

output "effective_oidc_provider_arn" {
  description = "Effective AWS IAM OIDC provider ARN used in IAM trust policy."
  value       = local.effective_oidc_provider_arn
}

output "kms_key_arn" {
  description = "KMS key ARN used by Secrets Manager."
  value       = aws_kms_key.secrets.arn
}

output "secret_names" {
  description = "Secrets Manager secret names referenced by manifests/30-external-secret.yaml."
  value       = local.secret_names
}

output "namespace" {
  description = "Kubernetes namespace expected by IAM trust policy."
  value       = var.namespace
}

output "service_account_name" {
  description = "Kubernetes service account expected by IAM trust policy."
  value       = var.service_account_name
}
