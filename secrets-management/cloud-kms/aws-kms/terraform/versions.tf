terraform {
  required_version = ">= 1.5.0"

  required_providers {
    coreweave = {
      source  = "coreweave/coreweave"
      version = ">= 0.3.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
