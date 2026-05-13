provider "coreweave" {
  token = var.coreweave_api_token
}

provider "google" {
  project = var.project_id
  region  = var.gcp_region
}
