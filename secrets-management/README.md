# Secrets Management Reference Architectures

This directory contains end-to-end reference architectures for managing application secrets on CoreWeave Kubernetes Service (CKS).

All references use External Secrets Operator (ESO) as the Kubernetes abstraction layer and expose the same runtime secret contract:

- `DB_USERNAME`
- `DB_PASSWORD`
- `API_TOKEN`

## Architectures

| Architecture | Backend | Auth Model | Path |
| --- | --- | --- | --- |
| Cloud KMS (AWS) | AWS Secrets Manager encrypted by AWS KMS | OIDC federation from CKS -> AWS STS short-lived role creds | [`cloud-kms/aws-kms/`](./cloud-kms/aws-kms/README.md) |
| Cloud KMS (GCP) | Google Secret Manager encrypted by Cloud KMS (CMEK) | OIDC federation from CKS -> GCP Workload Identity short-lived creds | [`cloud-kms/gcp-kms/`](./cloud-kms/gcp-kms/README.md) |

## Shared Prerequisites

- CoreWeave account permissions to create a VPC and CKS cluster.
- A CoreWeave API token exported as `TF_VAR_coreweave_api_token`.
- `kubectl`, `helm`, and provider CLIs (`aws`, `gcloud`) installed as needed.

After Terraform creates the CKS cluster and you download kubeconfig, install External Secrets Operator once per cluster:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
kubectl rollout status deployment/external-secrets -n external-secrets
```

## Validation Pattern (All Architectures)

1. Apply Terraform for the selected architecture. Each example creates its own VPC, CKS cluster, KMS key, and provider secret backend.
2. Download kubeconfig for the new CKS cluster from CoreWeave Console.
3. Ensure the cluster has schedulable node capacity before installing workloads.
4. Install ESO on that cluster.
5. Apply manifests for the selected architecture.
6. Confirm ESO reconciles:

```bash
kubectl get externalsecret -A
```

7. Confirm generated Kubernetes Secret exists:

```bash
kubectl get secret app-runtime-secrets -n <namespace>
```

8. Confirm workload can read synced values:

```bash
kubectl logs deployment/secrets-demo -n <namespace>
```
