# GCP KMS + Secret Manager Reference

This reference uses Google Secret Manager for secret storage, Cloud KMS (CMEK) for encryption at rest, and External Secrets Operator (ESO) for Kubernetes sync.

## Architecture

1. CKS OIDC issuer is configured as a trusted identity source in a GCP Workload Identity Pool.
2. ESO uses Kubernetes service account identity to obtain short-lived GCP credentials.
3. ESO reads secrets from Secret Manager (encrypted with a customer-managed Cloud KMS key).
4. ESO syncs secrets into Kubernetes `app-runtime-secrets`.

No static GCP service account key file is required.

## Prerequisites

- CKS cluster + ESO installed.
- GCP project with permissions to manage:
  - Workload Identity Federation
  - Cloud KMS
  - Secret Manager
  - IAM bindings
- (Recommended) CKS provisioned with this repository's Terraform stack so `cks_service_account_oidc_issuer_url` is available as an output.
- Terraform installed.

## Configure GCP Workload Identity Federation

This Terraform stack can create Workload Identity Pool + OIDC provider automatically from the CKS issuer URL.
It can also reuse an existing pool/provider if needed.

Your IAM member for a specific Kubernetes service account should resolve to:

`principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/system:serviceaccount:<NAMESPACE>:<SERVICE_ACCOUNT_NAME>`

This is the principal Terraform grants `roles/secretmanager.secretAccessor` permissions.

## Provision GCP Resources

From this directory:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Set values in `terraform.tfvars`:
- `project_id`
- `project_number`
- `cks_remote_state_*` (recommended) to auto-read `cks_service_account_oidc_issuer_url` from the CKS Terraform state.
- `workload_identity_pool_id`
- `secret_values`

If you cannot use `terraform_remote_state`, set:
- `cks_oidc_issuer_url` directly.

By default, this stack creates Workload Identity Pool + Provider (`create_workload_identity_pool=true`).
If your organization manages those centrally, set:
- `create_workload_identity_pool = false`
- `workload_identity_pool_id = <existing-pool-id>`

Then apply:

```bash
terraform init
terraform plan
terraform apply
```

Capture outputs:

```bash
terraform output
```

You need:
- `secret_names`
- `workload_identity_principal`
- `effective_cks_oidc_issuer_url`

## Configure and Apply Manifests

1. Update:
- `manifests/20-secret-store.yaml`: `projectID`
- If Terraform defaults were changed, update secret names in `manifests/30-external-secret.yaml`.

2. Apply:

```bash
kubectl apply -f manifests/00-namespace.yaml
kubectl apply -f manifests/10-service-account.yaml
kubectl apply -f manifests/20-secret-store.yaml
kubectl apply -f manifests/30-external-secret.yaml
kubectl apply -f manifests/40-demo-app.yaml
```

## Verify

```bash
kubectl get secretstore,externalsecret -n secrets-gcp
kubectl get secret app-runtime-secrets -n secrets-gcp
kubectl logs deployment/secrets-demo -n secrets-gcp
```

## Rotation Test

Rotate a secret in Secret Manager:

```bash
printf "rotated-password-%s" "$(date +%s)" | \
  gcloud secrets versions add ra-demo-db-password \
    --project <PROJECT_ID> \
    --data-file=-
```

Wait for ESO refresh (1m), then verify Kubernetes Secret updated:

```bash
kubectl get secret app-runtime-secrets -n secrets-gcp -o yaml
```
