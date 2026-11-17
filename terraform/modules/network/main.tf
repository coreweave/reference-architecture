# VPC with named prefixes for CKS (pod, service, internal LB CIDRs) and optional private access
# https://registry.terraform.io/providers/coreweave/coreweave/latest/docs/resources/networking_vpc
resource "coreweave_networking_vpc" "main" {
  name = var.name
  zone = var.zone

  # Optional: host_prefixes for compute; leave empty to use zone default
  host_prefixes = var.host_prefixes

  # Named prefixes passed through as-is, including the optional `type` attribute.
  # The root module derives CKS pod/service/internal LB names from these.
  vpc_prefixes = var.vpc_prefixes

  # Only send a dhcp block when DNS settings are provided; otherwise keep the zone defaults.
  dhcp = var.dhcp_dns_servers == null && var.dhcp_dns_search_domains == null ? null : {
    dns = {
      servers        = var.dhcp_dns_servers
      search_domains = var.dhcp_dns_search_domains
    }
  }
}
