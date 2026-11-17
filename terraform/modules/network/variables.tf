variable "name" {
  type        = string
  description = "VPC name (max 30 characters)"
}

variable "zone" {
  type        = string
  description = "CoreWeave zone (e.g. US-EAST-02A)"
}

variable "host_prefixes" {
  type = set(object({
    name     = string
    type     = string # PRIMARY, ROUTED, ATTACHED
    prefixes = list(string)
  }))
  description = "Host prefix definitions; provider requires at least one (e.g. PRIMARY with /18 CIDR)"
}

variable "vpc_prefixes" {
  type = list(object({
    name  = string
    value = string           # CIDR
    type  = optional(string) # POD, SERVICE, LOAD_BALANCER, PRIVATE_ACCESS (requires provider >= 0.28.0)
  }))
  description = <<-EOT
    Named VPC prefixes (e.g. pod cidr, service cidr, internal lb cidr, private access).
    `type` is optional and declares the prefix's intended use: POD, SERVICE, LOAD_BALANCER or PRIVATE_ACCESS.
    It must be declared here (and in any wrapping module) or Terraform/OpenTofu silently drops it
    before the provider sees it.
  EOT

  validation {
    condition = alltrue([
      for p in var.vpc_prefixes :
      p.type == null || contains(["POD", "SERVICE", "LOAD_BALANCER", "PRIVATE_ACCESS"], p.type)
    ])
    error_message = "vpc_prefixes[*].type must be one of POD, SERVICE, LOAD_BALANCER, PRIVATE_ACCESS, or omitted."
  }
}

variable "dhcp_dns_servers" {
  type        = set(string)
  description = "DNS servers handed out by DHCP within the VPC. Leave null to use the zone default resolvers. If you set custom resolvers, keep the zone default resolver in the list unless your resolvers can resolve CoreWeave domains, or nodes may fail to boot."
  default     = null
}

variable "dhcp_dns_search_domains" {
  type        = list(string)
  description = "DNS search domains handed out by DHCP within the VPC, in order of precedence. Leave null to leave unset."
  default     = null
}
