variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "project_number" {
  description = "GCP project number used to build Workload Identity principal strings."
  type        = string
}

variable "gcp_region" {
  description = "Default region for provider operations."
  type        = string
  default     = "us-central1"
}

variable "kms_location" {
  description = "Cloud KMS location for the key ring and crypto key."
  type        = string
  default     = "us-central1"
}

variable "secret_replica_location" {
  description = "Secret Manager replica location used for user-managed replication."
  type        = string
  default     = "us-central1"
}

variable "kms_key_ring_name" {
  description = "KMS key ring name."
  type        = string
  default     = "ra-secrets-ring"
}

variable "kms_key_name" {
  description = "KMS crypto key name."
  type        = string
  default     = "ra-secrets-key"
}

variable "secret_name_prefix" {
  description = "Prefix used to name Secret Manager secrets."
  type        = string
  default     = "ra-demo"
}

variable "namespace" {
  description = "Kubernetes namespace used by the GCP SecretStore and auth service account."
  type        = string
  default     = "secrets-gcp"
}

variable "service_account_name" {
  description = "Kubernetes service account used by ESO for GCP workload identity."
  type        = string
  default     = "eso-gcp-auth"
}

variable "workload_identity_pool_id" {
  description = "Workload Identity Pool ID. Required when create_workload_identity_pool=true, or when reusing an existing pool."
  type        = string
  default     = null
}

variable "workload_identity_provider_id" {
  description = "Workload Identity Pool Provider ID used when create_workload_identity_pool=true."
  type        = string
  default     = "cks-oidc"
}

variable "create_workload_identity_pool" {
  description = "When true, create Workload Identity Pool + OIDC Provider using the effective CKS OIDC issuer URL."
  type        = bool
  default     = true
}

variable "cks_oidc_issuer_url" {
  description = "Optional explicit CKS OIDC issuer URL. If unset, this can be sourced from cks_remote_state outputs."
  type        = string
  default     = null
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

variable "wif_subject" {
  description = "Optional custom workload identity subject. If null, defaults to system:serviceaccount:<namespace>:<service_account_name>."
  type        = string
  default     = null
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
