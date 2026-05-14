# PVC Migrate

Migrate a PVC between Kubernetes clusters using rclone via WebDAV over HTTPS.

## How it works

1. Deploys an **rclone server** on the source cluster that serves the PVC over WebDAV (HTTPS)
2. Deploys an **rclone client job** on the target cluster that syncs data into the target PVC
3. The server uses a self-signed TLS cert (via cert-manager) and password auth
4. The password is obfuscated for the client config to match rclone's format

## Prerequisites

- `kubectl` configured for both source and target clusters
- `rclone` CLI installed locally (for password obfuscation)
- cert-manager installed on the source cluster
- Target PVC and namespace created on target cluster
  - You can use the yaml/pvc.yaml template to create it if needed

## Usage

```bash
./pvcmigrate \
  --pvc <pvc-name> \
  --src-ns <source-namespace> \
  --tgt-ns <target-namespace> \
  --src-ctx <source-kube-context> \
  --tgt-ctx <target-kube-context> \
  --src-kubeconfig <source-kubeconfig-path> \
  --tgt-kubeconfig <target-kubeconfig-path>
```
