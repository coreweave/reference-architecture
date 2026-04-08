output "eso_role_arn" {
  description = "IAM role ARN to place in manifests/20-secret-store.yaml."
  value       = aws_iam_role.eso_reader.arn
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
