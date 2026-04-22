# AWS KMS + Secrets Manager Reference

This reference uses AWS Secrets Manager for secret storage, AWS KMS for encryption at rest, and External Secrets Operator (ESO) for Kubernetes sync.

## Architecture

1. CKS workload identity (service account token) is federated to AWS via IAM OIDC provider.
2. ESO assumes an AWS IAM role using short-lived web identity credentials.
3. ESO reads secrets from AWS Secrets Manager (encrypted by a customer-managed KMS key).
4. ESO syncs secrets into Kubernetes `app-runtime-secrets`.

No static AWS access key or secret key is required.

## Prerequisites

- CKS cluster + ESO installed.
- AWS account with permissions to create:
  - IAM role/policy
  - IAM OIDC provider (if `create_oidc_provider=true`)
  - KMS key
  - Secrets Manager secrets
- (Recommended) CKS provisioned with this repository's Terraform stack so `cks_service_account_oidc_issuer_url` is available as an output.
- Terraform installed.

`cks_service_account_oidc_issuer_url` comes from the read-only `service_account_oidc_issuer_url` field on `coreweave_cks_cluster`.

## Provision AWS Resources

From this directory:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Set values in `terraform.tfvars`:
- `cks_remote_state_*` (recommended) to auto-read `cks_service_account_oidc_issuer_url` from the CKS Terraform state.
- `secret_values` (bootstrap values)

If you cannot use `terraform_remote_state`, set:
- `oidc_issuer_url` directly.

By default, this stack creates an AWS IAM OIDC provider from the effective issuer URL (`create_oidc_provider=true`).
If your organization manages that provider elsewhere, set:
- `create_oidc_provider = false`
- `oidc_provider_arn = <existing-provider-arn>`

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
- `eso_role_arn`
- `secret_names`
- `effective_oidc_issuer_url`
- `effective_oidc_provider_arn`

## Configure and Apply Manifests

1. Update:
- `manifests/20-secret-store.yaml`
  - `region`
  - `role` (use `eso_role_arn`)
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
kubectl get secretstore,externalsecret -n secrets-aws
kubectl get secret app-runtime-secrets -n secrets-aws
kubectl logs deployment/secrets-demo -n secrets-aws
```

## Rotation Test

Rotate a secret in AWS:

```bash
aws secretsmanager put-secret-value \
  --secret-id ra-demo/db-password \
  --secret-string "rotated-password-$(date +%s)"
```

Wait for ESO refresh (1m), then verify the Kubernetes Secret updated:

```bash
kubectl get secret app-runtime-secrets -n secrets-aws -o yaml
```
