variable "cluster_name" {
  type        = string
  description = "CKS cluster name (max 30 characters)"
  default     = "my-cks-cluster"
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
  default     = true
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

variable "oidc" {
  type = object({
    issuer_url = string
    client_id  = string
    ca         = optional(string)
  })
  description = "OIDC config for the cluster (external IdP). Omit or set to null to leave unset."
  default     = null
}

variable "authn_webhook" {
  type = object({
    server = string
    ca     = optional(string)
  })
  description = "Authentication webhook config. Omit or set to null to leave unset."
  default     = null
}

variable "authz_webhook" {
  type = object({
    server = string
    ca     = optional(string)
  })
  description = "Authorization webhook config. Omit or set to null to leave unset."
  default     = null
}

variable "node_port_range" {
  type = object({
    start = number
    end   = number
  })
  description = "NodePort range (start/end). Omit or set to null to use cluster default."
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
