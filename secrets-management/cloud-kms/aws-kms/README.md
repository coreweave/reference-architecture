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
  - KMS key
  - Secrets Manager secrets
- CKS OIDC issuer URL available from cluster details.
- IAM OIDC provider configured in AWS for the CKS issuer URL.
- Terraform installed.

## Provision AWS Resources

From this directory:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Set values in `terraform.tfvars`:
- `oidc_issuer_url`
- `oidc_provider_arn`
- `secret_values` (bootstrap values)

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
