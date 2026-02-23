# Network (VPC) – created first; vpc_prefixes names must match CKS module
module "network" {
  source = "./modules/network"

  name         = var.vpc_name
  zone         = var.zone
  vpc_prefixes = var.vpc_prefixes
  host_prefixes = var.host_prefixes
}

# CKS cluster – depends on VPC; CIDR names must match VPC vpc_prefixes
module "cks" {
  source = "./modules/cks"

  cluster_name         = var.cluster_name
  kubernetes_version   = var.kubernetes_version
  zone                 = var.zone
  vpc_id               = module.network.vpc_id
  public               = var.cks_public
  pod_cidr_name        = var.pod_cidr_name
  service_cidr_name    = var.service_cidr_name
  internal_lb_cidr_names = var.internal_lb_cidr_names

  oidc_issuer_url = var.oidc_issuer_url
  oidc_client_id  = var.oidc_client_id
  oidc_ca         = var.oidc_ca

  authn_webhook_server = var.authn_webhook_server
  authn_webhook_ca     = var.authn_webhook_ca
  authz_webhook_server = var.authz_webhook_server
  authz_webhook_ca     = var.authz_webhook_ca

  node_port_start = var.node_port_start
  node_port_end   = var.node_port_end
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
