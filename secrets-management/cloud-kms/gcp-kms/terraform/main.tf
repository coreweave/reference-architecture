locals {
  cks_pod_cidr_name             = var.vpc_prefixes[0].name
  cks_service_cidr_name         = var.vpc_prefixes[1].name
  cks_internal_lb_cidr_names    = toset([for i in range(2, length(var.vpc_prefixes)) : var.vpc_prefixes[i].name])
  effective_cks_oidc_issuer_url = module.cks.service_account_oidc_issuer_url
  effective_wif_subject         = coalesce(var.wif_subject, "system:serviceaccount:${var.namespace}:${var.service_account_name}")
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
    condition     = var.workload_identity_pool_id != null && trimspace(var.workload_identity_pool_id) != ""
    error_message = "workload_identity_pool_id must be set."
  }
}

module "network" {
  source = "../../../../terraform/modules/network"

  name          = var.vpc_name
  zone          = var.zone
  vpc_prefixes  = var.vpc_prefixes
  host_prefixes = var.host_prefixes
}

module "cks" {
  source = "../../../../terraform/modules/cks"

  cluster_name           = var.cluster_name
  kubernetes_version     = var.kubernetes_version
  zone                   = module.network.vpc_zone
  vpc_id                 = module.network.vpc_id
  public                 = var.cks_public
  pod_cidr_name          = local.cks_pod_cidr_name
  service_cidr_name      = local.cks_service_cidr_name
  internal_lb_cidr_names = local.cks_internal_lb_cidr_names
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
