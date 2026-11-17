# Already in providers.tf: coreweave_api_token

variable "zone" {
  type        = string
  description = "CoreWeave zone (e.g. US-EAST-02A)"
}

variable "vpc_name" {
  type        = string
  description = "VPC name"
}

# VPC prefixes. Set `type` on each prefix (recommended); CKS prefix names are then derived from type:
#   POD -> pod CIDR, SERVICE -> service CIDR, LOAD_BALANCER -> internal LB CIDR(s),
#   PRIVATE_ACCESS -> private access prefix (never passed to CKS).
# If no prefix has a POD/SERVICE/LOAD_BALANCER type, the legacy positional convention applies to the
# non-PRIVATE_ACCESS prefixes: [0]=pod, [1]=service, [2..]=internal LB(s).
variable "vpc_prefixes" {
  type = list(object({
    name  = string
    value = string
    type  = optional(string) # POD, SERVICE, LOAD_BALANCER, PRIVATE_ACCESS (requires provider >= 0.28.0)
  }))
  description = "Named VPC CIDR prefixes. `type` (optional) is one of POD, SERVICE, LOAD_BALANCER, PRIVATE_ACCESS and drives which prefixes CKS uses. Without CKS types, order is used: first=pod, second=service, rest=internal LB(s)."

  validation {
    condition = alltrue([
      for p in var.vpc_prefixes :
      p.type == null || contains(["POD", "SERVICE", "LOAD_BALANCER", "PRIVATE_ACCESS"], p.type)
    ])
    error_message = "vpc_prefixes[*].type must be one of POD, SERVICE, LOAD_BALANCER, PRIVATE_ACCESS, or omitted."
  }

  validation {
    condition = (
      # Typed mode: exactly one POD, exactly one SERVICE, at least one LOAD_BALANCER
      length([for p in var.vpc_prefixes : p if contains(["POD", "SERVICE", "LOAD_BALANCER"], coalesce(p.type, "-"))]) == 0
      || (
        length([for p in var.vpc_prefixes : p if p.type == "POD"]) == 1 &&
        length([for p in var.vpc_prefixes : p if p.type == "SERVICE"]) == 1 &&
        length([for p in var.vpc_prefixes : p if p.type == "LOAD_BALANCER"]) >= 1
      )
    )
    error_message = "When using prefix types for CKS, define exactly one POD, exactly one SERVICE and at least one LOAD_BALANCER prefix."
  }

  validation {
    condition = (
      # Positional mode: at least 3 non-PRIVATE_ACCESS prefixes
      length([for p in var.vpc_prefixes : p if contains(["POD", "SERVICE", "LOAD_BALANCER"], coalesce(p.type, "-"))]) > 0
      || length([for p in var.vpc_prefixes : p if p.type != "PRIVATE_ACCESS"]) >= 3
    )
    error_message = "Without POD/SERVICE/LOAD_BALANCER types, at least 3 non-PRIVATE_ACCESS prefixes are required (pod, service, internal LB)."
  }
}

variable "vpc_dhcp_dns_servers" {
  type        = set(string)
  description = "Optional DNS servers handed out by DHCP within the VPC (e.g. your own resolvers over a private interconnect). Leave null for the zone default. If set, keep the zone default resolver in the list unless your resolvers can resolve CoreWeave domains, or nodes may fail to boot."
  default     = null
}

variable "vpc_dhcp_dns_search_domains" {
  type        = list(string)
  description = "Optional DNS search domains handed out by DHCP within the VPC. Leave null to leave unset."
  default     = null
}

variable "cks_internal_lb_cidr_names" {
  type        = set(string)
  description = "Optional override for the CKS internal LB CIDR prefix names. Leave null to derive them from vpc_prefixes. Use this to pin the existing value on an already-deployed cluster if the derived value would change."
  default     = null
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

variable "oidc" {
  type = object({
    issuer_url          = string
    client_id           = string
    ca                  = optional(string)
    admin_group_binding = optional(string)
    groups_claim        = optional(string)
    groups_prefix       = optional(string)
    required_claim      = optional(string)
    signing_algs        = optional(set(string))
    username_claim      = optional(string)
    username_prefix     = optional(string)
  })
  description = <<-EOT
    OIDC config for the CKS cluster (external IdP). Omit or set to null to leave unset.
    For workload identity federation with Object Storage, the CKS cluster's
    service_account_oidc_issuer_url (output) can be used as the issuer for
    exchanging K8s service account tokens for temporary Object Storage credentials.
  EOT
  default     = null
}

variable "authn_webhook" {
  type = object({
    server = string
    ca     = optional(string)
  })
  description = "Authentication webhook config for the CKS cluster. Omit or set to null to leave unset."
  default     = null
}

variable "authz_webhook" {
  type = object({
    server = string
    ca     = optional(string)
  })
  description = "Authorization webhook config for the CKS cluster. Omit or set to null to leave unset."
  default     = null
}

variable "node_port_range" {
  type = object({
    start = number
    end   = number
  })
  description = "NodePort range (start/end) for the CKS cluster. Omit or set to null to use cluster default."
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

# --- Object Storage organization access policies ---
variable "object_storage_org_access_policies" {
  type = map(object({
    statements = set(object({
      name       = string
      effect     = string
      actions    = set(string)
      resources  = set(string)
      principals = set(string)
    }))
  }))
  description = <<-EOT
    Map of organization-wide access policies for Object Storage. Map key = policy name.
    At least one must exist before creating a bucket. Use separate policies to isolate
    concerns (e.g. one for human users, one for OIDC/WIF roles, one for CI/CD).
    Each statement needs: name, effect (Allow/Deny), actions (s3:* or cwobject:*), resources, and principals.
    Principals use short-form identifiers (not full ARNs). For OIDC WIF roles: role/<ISSUER_URL>:<SUBJECT>
    Leave empty ({}) to skip (e.g. if policies are managed outside Terraform).
  EOT
  default     = {}
}

# --- Object Storage bucket access policy ---
variable "object_storage_bucket_policy_statements" {
  type = list(object({
    sid        = string
    effect     = string
    actions    = list(string)
    resources  = list(string)
    principals = map(list(string))
  }))
  description = <<-EOT
    Optional per-bucket access policy statements. Evaluated after organization access policies.
    Each statement needs: sid, effect (Allow/Deny), actions (e.g. ["s3:GetObject"]),
    resources (ARN format, e.g. ["arn:aws:s3:::my-bucket/*"]),
    principals (e.g. { "CW" = ["*"] } or { "CW" = ["arn:aws:iam::<org-id>:role/..."] }).
    Requires object_storage_bucket_name to be set. Set to null to skip.
  EOT
  default     = null
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
