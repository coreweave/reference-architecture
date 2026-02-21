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

  oidc = var.oidc_issuer_url != null ? {
    issuer_url = var.oidc_issuer_url
    client_id  = var.oidc_client_id
    ca         = var.oidc_ca
  } : null

  authn_webhook = var.authn_webhook_server != null ? {
    server = var.authn_webhook_server
    ca     = var.authn_webhook_ca
  } : null

  authz_webhook = var.authz_webhook_server != null ? {
    server = var.authz_webhook_server
    ca     = var.authz_webhook_ca
  } : null

  node_port_range = var.node_port_start != null && var.node_port_end != null ? {
    start = var.node_port_start
    end   = var.node_port_end
  } : null

  audit_policy = var.audit_policy
}
