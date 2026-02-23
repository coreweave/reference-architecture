# VPC with named prefixes for CKS (pod, service, internal LB CIDRs)
# https://registry.terraform.io/providers/coreweave/coreweave/latest/docs/resources/networking_vpc
resource "coreweave_networking_vpc" "main" {
  name = var.name
  zone = var.zone

  # Optional: host_prefixes for compute; leave empty to use zone default
  host_prefixes = var.host_prefixes

  # CKS cluster requires these named prefixes – names must match CKS module vars
  vpc_prefixes = var.vpc_prefixes
}
