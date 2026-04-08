locals {
  effective_wif_subject = coalesce(var.wif_subject, "system:serviceaccount:${var.namespace}:${var.service_account_name}")

  secret_names = {
    DB_USERNAME = "${var.secret_name_prefix}-db-username"
    DB_PASSWORD = "${var.secret_name_prefix}-db-password"
    API_TOKEN   = "${var.secret_name_prefix}-api-token"
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
  member    = "principal://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/${var.workload_identity_pool_id}/subject/${local.effective_wif_subject}"
}
