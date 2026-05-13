provider "coreweave" {
  token = var.coreweave_api_token
}

provider "aws" {
  region = var.aws_region
}
