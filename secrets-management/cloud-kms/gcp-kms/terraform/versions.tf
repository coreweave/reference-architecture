terraform {
  required_version = ">= 1.5.0"

  required_providers {
    coreweave = {
      source  = "coreweave/coreweave"
      version = ">= 0.3.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
  }
}
