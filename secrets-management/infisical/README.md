# Infisical Reference Architecture

This reference shows how to sync Infisical secrets into Kubernetes using External Secrets Operator (ESO), with Kubernetes-native authentication.

## Architecture

1. ESO uses a Kubernetes service account token to authenticate with Infisical Machine Identity (Kubernetes Auth).
2. ESO reads secrets from Infisical project/environment/path scope.
3. ESO writes a Kubernetes Secret (`app-runtime-secrets`) for workload consumption.
4. Secret rotation is handled by updating values in Infisical and letting ESO reconcile.

## Prerequisites

- CKS cluster and ESO installed.
- Infisical project with secrets:
  - `DB_USERNAME`
  - `DB_PASSWORD`
  - `API_TOKEN`
- Infisical Machine Identity configured for Kubernetes Auth.
- TokenReview permissions configured per Infisical Kubernetes Auth docs.

## Setup

1. Update these placeholders:
- `manifests/15-auth-secret.yaml`: set `identityId`.
- `manifests/20-secret-store.yaml`: set `hostAPI`, `projectSlug`, `environmentSlug`, `secretsPath`.
- If you change namespace/service account, update all manifest files consistently.

2. Apply manifests:

```bash
kubectl apply -f manifests/00-namespace.yaml
kubectl apply -f manifests/10-service-account.yaml
kubectl apply -f manifests/15-auth-secret.yaml
kubectl apply -f manifests/20-secret-store.yaml
kubectl apply -f manifests/30-external-secret.yaml
kubectl apply -f manifests/40-demo-app.yaml
```

## Verify

```bash
kubectl get secretstore,externalsecret -n secrets-infisical
kubectl get secret app-runtime-secrets -n secrets-infisical
kubectl logs deployment/secrets-demo -n secrets-infisical
```

Expected log lines should confirm all three keys are loaded.

## Rotation Test

1. Update one secret value in Infisical (for example `DB_PASSWORD`).
2. Wait for ESO refresh interval (configured as 1m).
3. Confirm Kubernetes Secret version changed:

```bash
kubectl get secret app-runtime-secrets -n secrets-infisical -o yaml
```
