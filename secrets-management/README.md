# Secrets Management Reference Architectures

This directory contains end-to-end reference architectures for managing application secrets on CoreWeave Kubernetes Service (CKS).

All references use External Secrets Operator (ESO) as the Kubernetes abstraction layer and expose the same runtime secret contract:

- `DB_USERNAME`
- `DB_PASSWORD`
- `API_TOKEN`

## Architectures

| Architecture | Backend | Auth Model | Path |
| --- | --- | --- | --- |
| Infisical | Infisical Secrets Platform | Kubernetes-native auth (service-account token) | [`infisical/`](./infisical/README.md) |

## Shared Prerequisites

- A running CKS cluster.
- `kubectl`, `helm`, and provider CLIs (`aws`, `gcloud`) installed as needed.
- External Secrets Operator installed once per cluster:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
kubectl rollout status deployment/external-secrets -n external-secrets
```

## Validation Pattern (All Architectures)

1. Apply manifests for the selected architecture.
2. Confirm ESO reconciles:

```bash
kubectl get externalsecret -A
```

3. Confirm generated Kubernetes Secret exists:

```bash
kubectl get secret app-runtime-secrets -n <namespace>
```

4. Confirm workload can read synced values:

```bash
kubectl logs deployment/secrets-demo -n <namespace>
```
