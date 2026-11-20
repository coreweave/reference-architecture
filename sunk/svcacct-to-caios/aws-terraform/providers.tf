terraform {
  required_version = ">= 1.5"

  required_providers {
    coreweave = {
      source  = "coreweave/coreweave"
      version = ">=0.25.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "6.68.0"
    }
  }
}

provider "coreweave" {} # COREWEAVE_API_TOKEN

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Terraform = "true"
    }
  }
}
