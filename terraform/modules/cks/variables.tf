variable "cluster_name" {
  type        = string
  description = "CKS cluster name (max 30 characters)"
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes minor version (e.g. v1.35)"
}

variable "zone" {
  type        = string
  description = "CoreWeave zone (e.g. US-EAST-02A)"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID from network module"
}

variable "public" {
  type        = bool
  description = "Whether the cluster API is publicly accessible"
  default     = false
}

variable "pod_cidr_name" {
  type        = string
  description = "Name of VPC prefix to use as pod CIDR (must exist in cluster VPC)"
}

variable "service_cidr_name" {
  type        = string
  description = "Name of VPC prefix to use as service CIDR (must exist in cluster VPC)"
}

variable "internal_lb_cidr_names" {
  type        = set(string)
  description = "Names of VPC prefixes for internal load balancer CIDRs (must exist in cluster VPC)"
}

variable "oidc_issuer_url" {
  type        = string
  description = "OIDC issuer URL for the cluster"
  default     = null
}

variable "oidc_client_id" {
  type        = string
  description = "OIDC client ID"
  default     = null
}

variable "oidc_ca" {
  type        = string
  description = "Base64-encoded PEM CA certificate for OIDC issuer"
  default     = null
}

variable "authn_webhook_server" {
  type        = string
  description = "Authentication webhook server URL"
  default     = null
}

variable "authn_webhook_ca" {
  type        = string
  description = "Base64-encoded PEM CA for authn webhook"
  default     = null
}

variable "authz_webhook_server" {
  type        = string
  description = "Authorization webhook server URL"
  default     = null
}

variable "authz_webhook_ca" {
  type        = string
  description = "Base64-encoded PEM CA for authz webhook"
  default     = null
}

variable "node_port_start" {
  type        = number
  description = "Start of NodePort range"
  default     = null
}

variable "node_port_end" {
  type        = number
  description = "End of NodePort range"
  default     = null
}

variable "audit_policy" {
  type        = string
  description = "Base64-encoded audit policy YAML/JSON"
  default     = null
}

variable "create_timeout" {
  type        = string
  description = "Timeout for cluster creation"
  default     = "45m"
}
