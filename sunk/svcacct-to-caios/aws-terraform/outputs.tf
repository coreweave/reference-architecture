output "role_arn" {
  value = aws_iam_role.slurm_identity.arn
}

output "bucket_name" {
  value = var.bucket_name
}

output "oidc_issuer" {
  value = local.cks_oidc_issuer
}
