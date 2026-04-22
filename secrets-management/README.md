# Secrets Management Reference Architectures

This directory contains end-to-end reference architectures for managing application secrets on CoreWeave Kubernetes Service (CKS).

## Architectures

| Architecture | Backend | Auth Model | Path |
| --- | --- | --- | --- |
| ESO | External Secrets Operator control plane baseline | Shared Kubernetes operator, controller-class scoped | [`eso/`](./eso/README.md) |

## Shared Prerequisites

- A running CKS cluster.
- `kubectl` and `helm` installed and configured.

## Validation Pattern

1. Deploy the reference architecture.
2. Confirm operator health:

```bash
kubectl get pods -n external-secrets
```

3. Confirm ESO CRDs are present:

```bash
kubectl get crd | rg external-secrets.io
```
