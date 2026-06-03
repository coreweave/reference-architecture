variable "coreweave_api_token" {
  description = "CoreWeave API token used to provision the VPC and CKS cluster. Prefer TF_VAR_coreweave_api_token."
  type        = string
  sensitive   = true
}

variable "zone" {
  description = "CoreWeave zone for the VPC and CKS cluster."
  type        = string
}

variable "vpc_name" {
  description = "CoreWeave VPC name."
  type        = string
  default     = "ra-secrets-aws-vpc"
}

variable "vpc_prefixes" {
  description = "Named VPC CIDR prefixes for CKS. Order: first=pod, second=service, remaining=internal LB."
  type = list(object({
    name  = string
    value = string
  }))
  default = [
    { name = "pod cidr", value = "10.0.0.0/13" },
    { name = "service cidr", value = "10.16.0.0/22" },
    { name = "internal lb cidr", value = "10.32.4.0/22" },
  ]

  validation {
    condition     = length(var.vpc_prefixes) >= 3
    error_message = "vpc_prefixes must include at least pod, service, and one internal load balancer CIDR."
  }
}

variable "host_prefixes" {
  description = "CoreWeave VPC host prefix definitions."
  type = set(object({
    name     = string
    type     = string
    prefixes = list(string)
  }))
  default = [
    { name = "primary", type = "PRIMARY", prefixes = ["10.16.192.0/18"] }
  ]
}

variable "cluster_name" {
  description = "CKS cluster name."
  type        = string
  default     = "ra-secrets-aws-cks"
}

variable "kubernetes_version" {
  description = "CKS Kubernetes minor version."
  type        = string
  default     = "v1.35"
}

variable "cks_public" {
  description = "Whether the CKS API server is publicly reachable."
  type        = bool
  default     = true
}

variable "aws_region" {
  description = "AWS region for KMS and Secrets Manager."
  type        = string
  default     = "us-east-1"
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
