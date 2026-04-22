data "terraform_remote_state" "cks" {
  count = var.cks_remote_state_backend == null ? 0 : 1

  backend = var.cks_remote_state_backend
  config  = var.cks_remote_state_config
}

locals {
  effective_cks_oidc_issuer_url = coalesce(
    var.cks_oidc_issuer_url,
    try(data.terraform_remote_state.cks[0].outputs.cks_service_account_oidc_issuer_url, null)
  )

  effective_wif_subject = coalesce(var.wif_subject, "system:serviceaccount:${var.namespace}:${var.service_account_name}")
  effective_workload_identity_pool_id = coalesce(
    var.workload_identity_pool_id,
    try(google_iam_workload_identity_pool.cks[0].workload_identity_pool_id, null)
  )

  secret_names = {
    DB_USERNAME = "${var.secret_name_prefix}-db-username"
    DB_PASSWORD = "${var.secret_name_prefix}-db-password"
    API_TOKEN   = "${var.secret_name_prefix}-api-token"
  }
}

check "workload_identity_pool_id_present" {
  assert {
    condition     = var.workload_identity_pool_id != null && trim(var.workload_identity_pool_id) != ""
    error_message = "workload_identity_pool_id must be set."
  }
}

check "oidc_issuer_url_present_when_creating_pool" {
  assert {
    condition = (
      !var.create_workload_identity_pool ||
      (local.effective_cks_oidc_issuer_url != null && trim(local.effective_cks_oidc_issuer_url) != "")
    )
    error_message = "An OIDC issuer URL is required when create_workload_identity_pool=true. Set cks_oidc_issuer_url directly or configure cks_remote_state_* to read cks_service_account_oidc_issuer_url from your CKS terraform outputs."
  }
}

resource "google_iam_workload_identity_pool" "cks" {
  count = var.create_workload_identity_pool ? 1 : 0

  project                   = var.project_id
  workload_identity_pool_id = var.workload_identity_pool_id
  display_name              = "CKS Secrets Workload Identity Pool"
  description               = "OIDC federation pool for CKS service account identities used by ESO."
}

resource "google_iam_workload_identity_pool_provider" "cks_oidc" {
  count = var.create_workload_identity_pool ? 1 : 0

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.cks[0].workload_identity_pool_id
  workload_identity_pool_provider_id = var.workload_identity_provider_id
  display_name                       = "CKS OIDC Provider"
  description                        = "OIDC provider wired to the CKS service_account_oidc_issuer_url."

  attribute_mapping = {
    "google.subject" = "assertion.sub"
  }

  oidc {
    issuer_uri = local.effective_cks_oidc_issuer_url
  }
}

resource "google_kms_key_ring" "secrets" {
  name     = var.kms_key_ring_name
  location = var.kms_location
  project  = var.project_id
}

resource "google_kms_crypto_key" "secrets" {
  name            = var.kms_key_name
  key_ring        = google_kms_key_ring.secrets.id
  rotation_period = "7776000s"
}

resource "google_kms_crypto_key_iam_member" "secret_manager_service_agent" {
  crypto_key_id = google_kms_crypto_key.secrets.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${var.project_number}@gcp-sa-secretmanager.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret" "app" {
  for_each = local.secret_names

  project   = var.project_id
  secret_id = each.value

  replication {
    user_managed {
      replicas {
        location = var.secret_replica_location
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.secrets.id
        }
      }
    }
  }
}

resource "google_secret_manager_secret_version" "app" {
  for_each = local.secret_names

  secret      = google_secret_manager_secret.app[each.key].id
  secret_data = var.secret_values[each.key]
}

resource "google_secret_manager_secret_iam_member" "eso_reader" {
  for_each = local.secret_names

  project   = var.project_id
  secret_id = google_secret_manager_secret.app[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "principal://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${local.effective_workload_identity_pool_id}/subject/${local.effective_wif_subject}"
}
