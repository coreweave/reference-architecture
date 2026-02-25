# CKS prefix names derived from vpc_prefixes (single source of truth)
# Convention: vpc_prefixes[0] = pod, [1] = service, [2..] = internal LB(s). Requires at least 3 entries.
locals {
  cks_pod_cidr_name         = var.vpc_prefixes[0].name
  cks_service_cidr_name     = var.vpc_prefixes[1].name
  cks_internal_lb_cidr_names = toset([for i in range(2, length(var.vpc_prefixes)) : var.vpc_prefixes[i].name])
}

# Network (VPC) – created first
module "network" {
  source = "./modules/network"

  name          = var.vpc_name
  zone          = var.zone
  vpc_prefixes  = var.vpc_prefixes
  host_prefixes = var.host_prefixes
}

# CKS cluster – depends on VPC; uses VPC's zone and prefix names derived from vpc_prefixes
module "cks" {
  source = "./modules/cks"

  cluster_name           = var.cluster_name
  kubernetes_version     = var.kubernetes_version
  zone                   = module.network.vpc_zone
  vpc_id                 = module.network.vpc_id
  public                 = var.cks_public
  pod_cidr_name          = local.cks_pod_cidr_name
  service_cidr_name      = local.cks_service_cidr_name
  internal_lb_cidr_names = local.cks_internal_lb_cidr_names

  oidc            = var.oidc
  authn_webhook   = var.authn_webhook
  authz_webhook   = var.authz_webhook
  node_port_range = var.node_port_range
  audit_policy    = var.audit_policy
}

# Object Storage bucket (optional; set object_storage_bucket_name to create)
module "object_storage" {
  source = "./modules/object_storage"

  bucket_name = var.object_storage_bucket_name
  zone        = coalesce(var.object_storage_bucket_zone, var.zone)
  tags        = var.object_storage_bucket_tags
}

# NodePools (optional; phase 2 – requires kubeconfig). Use nodepools map for multiple NodePools.
module "nodepool" {
  for_each = local.nodepools_to_create
  source   = "./modules/nodepool"

  create          = true
  name            = each.key
  instance_type   = each.value.instance_type
  target_nodes    = each.value.target_nodes
  autoscaling     = each.value.autoscaling
  min_nodes       = each.value.min_nodes
  max_nodes       = each.value.max_nodes
  node_labels     = each.value.node_labels
  node_annotations = each.value.node_annotations
  node_taints     = each.value.node_taints
}

# DFS PVCs (optional; phase 2 – requires kubeconfig for current cluster). Use dfs_pvcs map for multiple PVCs.
locals {
  nodepools_to_create = var.create_nodepool ? (length(var.nodepools) > 0 ? var.nodepools : {
    (var.nodepool_name) = {
      instance_type    = var.nodepool_instance_type
      target_nodes     = var.nodepool_target_nodes
      autoscaling      = var.nodepool_autoscaling
      min_nodes        = var.nodepool_min_nodes
      max_nodes        = var.nodepool_max_nodes
      node_labels      = var.nodepool_node_labels
      node_annotations = var.nodepool_node_annotations
      node_taints      = var.nodepool_node_taints
    }
  }) : {}
  dfs_pvcs_to_create = var.create_dfs_pvc ? (length(var.dfs_pvcs) > 0 ? var.dfs_pvcs : { (var.dfs_pvc_name) = { namespace = var.dfs_pvc_namespace, size = var.dfs_pvc_size } }) : {}
}

module "dfs" {
  for_each = local.dfs_pvcs_to_create
  source   = "./modules/dfs"

  create    = true
  pvc_name  = each.key
  namespace = each.value.namespace
  size      = each.value.size
}
