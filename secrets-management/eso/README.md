# External Secrets Operator (ESO) Reference Architecture

This reference defines a reusable ESO baseline for CKS clusters that consume external secret backends (Infisical, AWS Secrets Manager, GCP Secret Manager, and others).

## Architecture

1. ESO runs as a shared platform component in the `external-secrets` namespace.
2. A dedicated controller class (`platform-secrets`) is used to scope managed `SecretStore`/`ClusterSecretStore` resources.
3. Application namespaces define `ExternalSecret` resources that sync provider values into Kubernetes `Secret` objects.
4. Provider-specific store configuration is handled by each backend architecture guide under `secrets-management/`.

## Why This Exists

The Infisical and Cloud KMS guides depend on a working ESO control plane. This reference makes that prerequisite explicit and repeatable.

## Deploy

1. Create namespace and baseline labels:

```bash
kubectl apply -f manifests/00-namespace.yaml
```

2. Install ESO with the reference values:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace \
  -f helm-values.yaml
```

3. Verify controller health and CRDs:

```bash
kubectl get pods -n external-secrets
kubectl get crd | rg external-secrets.io
```

## Controller Class Usage

This reference sets:

```yaml
controllerClass: platform-secrets
```

To ensure the controller picks up intended stores, set `spec.controller: platform-secrets` on each `SecretStore` or `ClusterSecretStore`.

## Next Steps

Add provider-specific `SecretStore`/`ExternalSecret` references for your selected backend (for example Infisical, AWS Secrets Manager, or GCP Secret Manager) using this ESO baseline.
