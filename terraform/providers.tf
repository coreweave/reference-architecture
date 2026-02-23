terraform {
  required_providers {
    coreweave = {
      source  = "coreweave/coreweave"
      version = ">= 0.3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
    }
  }
  required_version = ">= 1.2.0"
}

variable "coreweave_api_token" {
  type      = string
  sensitive = true
}

# Optional: for object storage bucket operations. Defaults to https://cwobject.com if unset.
# Use http://cwlota.com when running from inside a CoreWeave cluster.
variable "coreweave_s3_endpoint" {
  type        = string
  default     = null
  description = "S3 endpoint for object storage (e.g. https://cwobject.com). Omit to use provider default."
}

provider "coreweave" {
  token       = var.coreweave_api_token
  s3_endpoint = var.coreweave_s3_endpoint
}

# Connect to CKS cluster for NodePool/DFS (phase 2). Set cks_kubeconfig_path after cluster exists (download kubeconfig from CoreWeave Console).
variable "cks_kubeconfig_path" {
  type        = string
  default     = null
  description = "Path to kubeconfig for the CKS cluster (optional; uses KUBECONFIG env or ~/.kube/config if unset)"
}

provider "kubernetes" {
  config_path = var.cks_kubeconfig_path
}