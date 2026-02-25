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
    value = string # CIDR
  }))
  description = "Named VPC prefixes for CKS (pod cidr, service cidr, internal lb cidr)"
}
