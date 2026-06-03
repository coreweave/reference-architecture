# GCP KMS + Secret Manager Tutorial

This tutorial provisions a disposable CoreWeave VPC and CKS cluster, creates Google Secret Manager secrets encrypted with Cloud KMS, and verifies that External Secrets Operator syncs them into Kubernetes via direct Workload Identity Federation (no GKE required).

## Prerequisites

- CoreWeave account permissions to create a VPC and CKS cluster.
- A CoreWeave API token exported as `TF_VAR_coreweave_api_token`.
- GCP credentials available to Terraform via Application Default Credentials (`gcloud auth application-default login`).
- A GCP project where you can grant the IAM roles below. Terraform enables the required APIs (`iam`, `iamcredentials`, `sts`, `cloudkms`, `secretmanager`) automatically.
- GCP IAM roles on your account (or a service account you impersonate):
  - `roles/iam.workloadIdentityPoolAdmin`
  - `roles/cloudkms.admin`
  - `roles/secretmanager.admin`
  - `roles/resourcemanager.projectIamAdmin` (or `roles/iam.securityAdmin`)
  - `roles/serviceusage.serviceUsageAdmin`
- Terraform `>= 1.5`, `kubectl`, `helm`, and `gcloud`.
- Access to CoreWeave Console to download kubeconfig for the new CKS cluster.

## 1. Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

- Set `zone`, `vpc_name`, and `cluster_name`.
- Set `project_id` and `project_number`.
- Set `workload_identity_pool_id`. Pick a value that has not been used recently in this project — GCP soft-deletes pools for 30 days and refuses to recreate the same ID within that window.
- Replace `secret_values`.
- Keep `create_workload_identity_pool = true` unless your GCP project already has a pool wired to this CKS issuer URL.

Set credentials:

```bash
export TF_VAR_coreweave_api_token="<COREWEAVE_API_TOKEN>"
gcloud auth application-default login
gcloud auth application-default set-quota-project "<PROJECT_ID>"
gcloud config set project "<PROJECT_ID>"
```

## 2. Provision

```bash
terraform init
terraform plan
terraform apply
terraform output
```

Record these outputs — you will paste them into manifests in step 5:

- `cks_cluster_name`
- `secret_names`
- `eso_audience` — the WIF provider resource path that ESO must use as both the STS exchange audience and the K8s ServiceAccount token audience.
- `workload_identity_principal` — the IAM principal granted Secret Manager access.

The terraform run takes about 5 minutes (most of it is CKS cluster creation). If CKS returns `Internal Error / unavailable` after the provider's 11 internal retries, the chosen zone is most likely temporarily unable to create new clusters; pick another zone and re-run.

## 3. Connect To CKS

Download kubeconfig for `cks_cluster_name` from CoreWeave Console, then point `kubectl` at it:

```bash
export KUBECONFIG="/path/to/downloaded/kubeconfig"
kubectl get nodes
```

If there are no schedulable nodes, create a NodePool. The example uses `cd-gp-i64-erapids`; not every CPU type is available in every zone, so check [Instance availability matrix](https://docs.coreweave.com/platform/instances/availability-matrix) and edit `manifests/cpu-nodepool.yaml` if you need a different `instanceType`.

```bash
kubectl apply -f ../manifests/cpu-nodepool.yaml
kubectl get nodepool cpu
kubectl wait --for=condition=Ready nodes --all --timeout=10m
```

If `kubectl get nodepool cpu` shows `VALIDATED=Invalid`, run `kubectl describe nodepool cpu` — the event log explains why (commonly `instance type does not exist in zone`).

## 4. Install ESO

The `workloadIdentityFederation` auth path used here requires ESO with the GCP WIF support shipped in late 2025.

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
kubectl rollout status deployment/external-secrets -n external-secrets
```

## 5. Update Manifests

Edit `../manifests/20-secret-store.yaml`:

- Set `spec.provider.gcpsm.projectID` to `project_id`.
- Set both `spec.provider.gcpsm.auth.workloadIdentityFederation.audience` and `spec.provider.gcpsm.auth.workloadIdentityFederation.serviceAccountRef.audiences[0]` to the `eso_audience` value from `terraform output`. They must be identical — the first drives the STS token exchange, the second drives the K8s TokenRequest `aud` claim. If they don't match, GCP rejects the federation with `The audience in ID Token does not match the expected audience.`

If you changed `secret_name_prefix`, update remote keys in `../manifests/30-external-secret.yaml` to match `secret_names`.

## 6. Apply Manifests

```bash
kubectl apply -f ../manifests/00-namespace.yaml
kubectl apply -f ../manifests/10-service-account.yaml
kubectl apply -f ../manifests/20-secret-store.yaml
kubectl apply -f ../manifests/30-external-secret.yaml
kubectl apply -f ../manifests/40-demo-app.yaml
```

## 7. Verify

```bash
kubectl get secretstore,externalsecret -n secrets-gcp
kubectl describe externalsecret app-secrets -n secrets-gcp
kubectl get secret app-runtime-secrets -n secrets-gcp
kubectl rollout status deployment/secrets-demo -n secrets-gcp
kubectl logs deployment/secrets-demo -n secrets-gcp
```

The SecretStore should report `Ready=True, Capabilities=ReadWrite`. The ExternalSecret should report `SecretSynced=True`. The demo logs should show:

```text
DB_USERNAME loaded
DB_PASSWORD loaded
API_TOKEN loaded
```

If the SecretStore reports `InvalidProviderConfig` with `audience ... does not match`, the two audience fields in step 5 are not identical or do not match the `eso_audience` output.

## 8. Test Rotation

```bash
printf "rotated-password-%s" "$(date +%s)" | \
  gcloud secrets versions add ra-demo-db-password \
    --project "<PROJECT_ID>" \
    --data-file=-
```

Wait at least one ESO refresh interval (default 60s), then verify the Kubernetes Secret changed:

```bash
kubectl get secret app-runtime-secrets -n secrets-gcp -o yaml
```

## 9. Clean Up

```bash
kubectl delete -f ../manifests/40-demo-app.yaml --ignore-not-found
kubectl delete -f ../manifests/30-external-secret.yaml --ignore-not-found
kubectl delete -f ../manifests/20-secret-store.yaml --ignore-not-found
kubectl delete -f ../manifests/10-service-account.yaml --ignore-not-found
kubectl delete -f ../manifests/00-namespace.yaml --ignore-not-found
terraform destroy
```

What `terraform destroy` does not fully clean up:

- **Cloud KMS key rings cannot be deleted in GCP.** The key ring resource is removed from terraform state, but the ring lingers in your project forever. Pick a unique `kms_key_ring_name` per run, or accept the leftover.
- Crypto key versions destroyed by terraform enter a 24-hour scheduled-destruction window before they are permanently gone.
- The Workload Identity Pool soft-deletes for 30 days. Recreating the same `workload_identity_pool_id` within that window fails — either pick a new ID or undelete the pool.
- The IAM bindings on each Secret Manager secret are torn down with the secret; nothing strands.
