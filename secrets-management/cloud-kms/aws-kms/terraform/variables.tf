variable "aws_region" {
  description = "AWS region for KMS and Secrets Manager."
  type        = string
  default     = "us-east-1"
}

variable "oidc_issuer_url" {
  description = "CKS OIDC issuer URL (for example: https://oidc.cks.coreweave.com/id/xxxxx)."
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the AWS IAM OIDC provider registered for the CKS issuer."
  type        = string
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
