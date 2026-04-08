variable "aws_region" {
  description = "AWS region for KMS and Secrets Manager."
  type        = string
  default     = "us-east-1"
}

variable "oidc_issuer_url" {
  description = "Optional explicit CKS OIDC issuer URL. If unset, this can be sourced from cks_remote_state outputs."
  type        = string
  default     = null
}

variable "oidc_provider_arn" {
  description = "Optional existing AWS IAM OIDC provider ARN. Required only when create_oidc_provider is false."
  type        = string
  default     = null
}

variable "create_oidc_provider" {
  description = "When true, create an AWS IAM OIDC provider from the effective CKS OIDC issuer URL."
  type        = bool
  default     = true
}

variable "cks_remote_state_backend" {
  description = "Optional terraform_remote_state backend for reading CKS outputs (for example: local, s3, gcs, remote)."
  type        = string
  default     = null
}

variable "cks_remote_state_config" {
  description = "Optional terraform_remote_state backend config map used when cks_remote_state_backend is set."
  type        = map(string)
  default     = {}
}

variable "namespace" {
  description = "Kubernetes namespace used by the AWS SecretStore and auth service account."
  type        = string
  default     = "secrets-aws"
}

variable "service_account_name" {
  description = "Kubernetes service account used by ESO for AWS web identity."
  type        = string
  default     = "eso-aws-auth"
}

variable "role_name" {
  description = "IAM role name that ESO assumes via web identity."
  type        = string
  default     = "ra-eso-aws-secrets-reader"
}

variable "kms_key_alias" {
  description = "Alias for the KMS key used to encrypt Secrets Manager secrets."
  type        = string
  default     = "alias/ra-secrets-kms"
}

variable "secret_name_prefix" {
  description = "Prefix used to name Secrets Manager secrets."
  type        = string
  default     = "ra-demo"
}

variable "secret_values" {
  description = "Bootstrap secret values keyed by DB_USERNAME, DB_PASSWORD, and API_TOKEN."
  type        = map(string)
  sensitive   = true

  validation {
    condition = (
      contains(keys(var.secret_values), "DB_USERNAME") &&
      contains(keys(var.secret_values), "DB_PASSWORD") &&
      contains(keys(var.secret_values), "API_TOKEN")
    )
    error_message = "secret_values must include DB_USERNAME, DB_PASSWORD, and API_TOKEN."
  }
}
