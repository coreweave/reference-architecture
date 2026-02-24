# CKS cluster – see CoreWeave provider docs:
# https://registry.terraform.io/providers/coreweave/coreweave/latest/docs/resources/cks_cluster
resource "coreweave_cks_cluster" "main" {
  name    = var.cluster_name
  version = var.kubernetes_version
  zone    = var.zone
  vpc_id  = var.vpc_id

  public = var.public

  # Names must match VPC prefix names from the network module
  pod_cidr_name          = var.pod_cidr_name
  service_cidr_name      = var.service_cidr_name
  internal_lb_cidr_names = var.internal_lb_cidr_names

  oidc           = var.oidc
  authn_webhook  = var.authn_webhook
  authz_webhook  = var.authz_webhook
  node_port_range = var.node_port_range

  audit_policy = var.audit_policy
}
