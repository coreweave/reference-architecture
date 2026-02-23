# Already in providers.tf: coreweave_api_token

variable "zone" {
  type        = string
  description = "CoreWeave zone (e.g. US-EAST-02A)"
}

variable "vpc_name" {
  type        = string
  description = "VPC name"
}

# VPC prefixes – names must match pod_cidr_name, service_cidr_name, internal_lb_cidr_names
variable "vpc_prefixes" {
  type = list(object({
    name  = string
    value = string
  }))
  description = "Named VPC CIDR prefixes for CKS (pod, service, internal lb)"
}

variable "host_prefixes" {
  type = set(object({
    name     = string
    type     = string
    prefixes = list(string)
  }))
  description = "Optional host prefix definitions; leave empty to use zone default"
  default     = []
}

variable "cluster_name" {
  type        = string
  description = "CKS cluster name (max 30 chars)"
  default     = "my-cks-cluster"
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes minor version (e.g. v1.35)"
}

variable "cks_public" {
  type        = bool
  description = "Whether the CKS cluster API is publicly accessible"
  default     = true
}

variable "pod_cidr_name" {
  type        = string
  description = "Name of VPC prefix for pod CIDR (must match vpc_prefixes[].name)"
}

variable "service_cidr_name" {
  type        = string
  description = "Name of VPC prefix for service CIDR (must match vpc_prefixes[].name)"
}

variable "internal_lb_cidr_names" {
  type        = set(string)
  description = "Names of VPC prefixes for internal LB CIDRs (must match vpc_prefixes[].name)"
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
  description = "Base64-encoded PEM CA for OIDC issuer"
  default     = null
}

variable "authn_webhook_server" {
  type        = string
  description = "Authentication webhook server URL"
  default     = null
}

variable "authn_webhook_ca" {
  type        = string
  default     = null
}

variable "authz_webhook_server" {
  type        = string
  description = "Authorization webhook server URL"
  default     = null
}

variable "authz_webhook_ca" {
  type        = string
  default     = null
}

variable "node_port_start" {
  type        = number
  description = "NodePort range start"
  default     = null
}

variable "node_port_end" {
  type        = number
  description = "NodePort range end"
  default     = null
}

variable "audit_policy" {
  type        = string
  description = "Base64-encoded audit policy YAML/JSON"
  default     = null
}

# --- CoreWeave AI Object Storage bucket ---
variable "object_storage_bucket_name" {
  type        = string
  description = "Object storage bucket name (globally unique; must not start with cw- or vip-)"
  default     = null
}

variable "object_storage_bucket_zone" {
  type        = string
  description = "Zone for the object storage bucket (e.g. US-EAST-02A); defaults to var.zone when null"
  default     = null
}

variable "object_storage_bucket_tags" {
  type        = map(string)
  description = "Tags to assign to the bucket"
  default     = {}
}

# --- CKS NodePool (kubernetes_manifest) ---
variable "create_nodepool" {
  type        = bool
  description = "Create NodePool(s) via Kubernetes provider. Set to false when cluster is missing or kubeconfig points at a deleted cluster (e.g. before first apply or after recreating cluster)."
  default     = false
}

# Multiple NodePools: map key = NodePool name, value = spec. When non-empty, used instead of single-nodepool vars below.
variable "nodepools" {
  type = map(object({
    instance_type    = string
    target_nodes     = number
    autoscaling      = bool
    min_nodes        = number
    max_nodes        = number
    node_labels      = map(string)
    node_annotations = map(string)
    node_taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  description = "Map of NodePools to create: name -> { instance_type, target_nodes, autoscaling, min_nodes, max_nodes, node_labels, node_annotations, node_taints }. Leave empty to use the single-nodepool vars below."
  default     = {}
}

# Single NodePool (used when nodepools is empty)
variable "nodepool_name" {
  type        = string
  description = "NodePool metadata name when using a single NodePool (ignored when nodepools is non-empty)"
  default     = "example-nodepool"
}

variable "nodepool_instance_type" {
  type        = string
  description = "CKS instance type for single NodePool (e.g. gd-8xh100ib-i128); ignored when nodepools is non-empty"
  default     = "gd-8xh100ib-i128"
}

variable "nodepool_target_nodes" {
  type        = number
  description = "Desired number of nodes for single NodePool; ignored when nodepools is non-empty"
  default     = 2
}

variable "nodepool_autoscaling" {
  type        = bool
  description = "Enable autoscaling for single NodePool; ignored when nodepools is non-empty"
  default     = false
}

variable "nodepool_min_nodes" {
  type        = number
  description = "Min nodes when autoscaling (single NodePool); ignored when nodepools is non-empty"
  default     = 0
}

variable "nodepool_max_nodes" {
  type        = number
  description = "Max nodes when autoscaling (single NodePool); ignored when nodepools is non-empty"
  default     = 0
}

variable "nodepool_node_labels" {
  type        = map(string)
  description = "Labels applied to nodes (single NodePool); ignored when nodepools is non-empty"
  default     = {}
}

variable "nodepool_node_annotations" {
  type        = map(string)
  description = "Annotations applied to nodes (single NodePool); ignored when nodepools is non-empty"
  default     = {}
}

variable "nodepool_node_taints" {
  type = list(object({
    key    = string
    value  = string
    effect = string # e.g. NoSchedule
  }))
  description = "Taints applied to nodes (single NodePool); ignored when nodepools is non-empty"
  default     = []
}

# --- CoreWeave DFS (Distributed File Storage) PVC (kubernetes_manifest) ---
variable "create_dfs_pvc" {
  type        = bool
  description = "Create DFS PVC(s) in the CKS cluster. Set to true after cluster exists and kubeconfig is set (same as NodePool)."
  default     = false
}

# Multiple DFS PVCs: map key = PVC name, value = namespace + size. When non-empty, this is used instead of the single-PVC vars below.
variable "dfs_pvcs" {
  type = map(object({
    namespace = string
    size      = string
  }))
  description = "Map of DFS PVCs to create: name -> { namespace, size }. Example: { \"dfs-shared\" = { namespace = \"default\", size = \"100Gi\" }, \"dfs-ml\" = { namespace = \"ml\", size = \"500Gi\" } }. Leave empty to use the single-PVC vars (dfs_pvc_name, dfs_pvc_namespace, dfs_pvc_size)."
  default     = {}
}

# Single-PVC (used when dfs_pvcs is empty)
variable "dfs_pvc_name" {
  type        = string
  description = "Name of the DFS PVC when using a single PVC (ignored when dfs_pvcs is non-empty)"
  default     = "dfs-shared"
}

variable "dfs_pvc_namespace" {
  type        = string
  description = "Namespace for the single DFS PVC (ignored when dfs_pvcs is non-empty)"
  default     = "default"
}

variable "dfs_pvc_size" {
  type        = string
  description = "Storage size for the single DFS PVC, e.g. 100Gi, 1Ti (ignored when dfs_pvcs is non-empty)"
  default     = "100Gi"
}
