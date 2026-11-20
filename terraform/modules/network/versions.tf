terraform {
  required_providers {
    coreweave = {
      source = "coreweave/coreweave"
      # >= 0.28.0 is required for vpc_prefixes[*].type; 0.29.0 is the tested baseline.
      version = ">= 0.29.0"
    }
  }
}
