# DFS Shared PVC Script

Full lifecycle management for sharing distributed file storage (DFS) persistent volumes across Kubernetes namespaces using VAST CSI driver.

## Overview

This script enables seamless sharing of distributed file storage volumes across multiple Kubernetes namespaces using the VAST CSI driver. It provides a complete command-line interface with subcommands for managing the entire lifecycle of shared DFS PVCs - from creation through validation, reconciliation, and cleanup.

## Prerequisites

- `kubectl` installed and configured
- Active connection to Kubernetes cluster
- Source PVC must use VAST CSI driver (`csi.vastdata.com`) for distributed file storage
- Target namespaces must exist

## Installation

```bash
# Download the script
curl -O https://raw.githubusercontent.com/coreweave/reference-architecture/main/storage/dfs-shared-pvc/share-pvc.sh

# Make executable
chmod +x share-pvc.sh

# Optional: Install to PATH
sudo mv share-pvc.sh /usr/local/bin/share-pvc
```

## How It Works

The script creates new PersistentVolume (PV) and PersistentVolumeClaim (PVC) resources that reference the same underlying VAST storage volume as the source PVC. This enables multiple namespaces to access the same data without copying it.

**Key Concepts:**
- **Source PVC**: The original PVC with data you want to share
- **Target PVC**: A new PVC in another namespace that accesses the same storage
- **Read-Only**: Target PVCs can be configured as read-only for safety
- **Labels**: All created resources are labeled for easy tracking and cleanup

**Resource Ownership:**
- Created PVs use `Retain` reclaim policy to prevent accidental data loss
- Resources are labeled with `coreweave.com/shared-by=dfs-shared-pvc-script`
- Source PVC is never modified or deleted
- Deleting a target PVC leaves the PV in Released state (data preserved)

## Commands

### apply - Create or Update Shares

Create shared PVCs from command-line arguments or manifest file.

**From Command Line:**
```bash
share-pvc apply \
  -s data-volume -n production \
  -t data-volume -N development \
  -t data-readonly -N analytics --read-only
```

**From Manifest:**
```bash
share-pvc apply -f shares.yaml
share-pvc apply -f shares.yaml --dry-run  # Preview changes
```

**Options:**
- `-s, --source-pvc NAME` - Source PVC name
- `-n, --source-namespace NS` - Source namespace
- `-t, --target-pvc NAME` - Target PVC name (repeatable)
- `-N, --target-namespace NS` - Target namespace (repeatable)
- `-r, --read-only` - Make preceding target read-only
- `-f, --file FILE` - YAML manifest file
- `-l, --label KEY=VALUE` - Additional labels (repeatable)
- `--dry-run` - Preview without creating
- `-v, --verbose` - Detailed output

### list - Show Existing Shares

Display all managed shared PVCs with filtering options.

```bash
# List all shares
share-pvc list

# Filter by source
share-pvc list --source production/data-volume

# Filter by target namespace
share-pvc list --target development

# JSON output
share-pvc list --output json
```

**Options:**
- `--source NS/PVC` - Filter by source
- `--target NS` - Filter by target namespace
- `--output FORMAT` - Output format: `table`, `json`, `yaml`
- `-v, --verbose` - Detailed information

### validate - Check Configuration

Validate manifest syntax and check state of existing shares.

```bash
# Validate manifest
share-pvc validate -f shares.yaml

# Check specific source
share-pvc validate --source production/data

# Check for drift
share-pvc validate --source production/data --check-drift
```

**Options:**
- `-f, --file FILE` - Manifest to validate
- `--source NS/PVC` - Validate specific source
- `--check-drift` - Check for configuration drift
- `-v, --verbose` - Detailed validation output

### delete - Remove Shares

Delete shared PVCs (removes derived PVs/PVCs, not source).

```bash
# Delete all shares from a source
share-pvc delete --source production/data

# Delete specific target
share-pvc delete --target development/data-shared

# Delete all managed shares (with confirmation)
share-pvc delete --all

# Force delete without confirmation
share-pvc delete --source production/data --force
```

**Options:**
- `--source NS/PVC` - Delete all shares from source
- `--target NS/PVC` - Delete specific target
- `--all` - Delete all managed shares
- `--force` - Skip confirmation
- `--dry-run` - Preview deletion
- `-v, --verbose` - Detailed output

### reconcile - Sync State with Manifest

Ensure actual state matches desired state in manifest.

```bash
# Reconcile to match manifest
share-pvc reconcile -f shares.yaml

# Preview changes
share-pvc reconcile -f shares.yaml --dry-run

# Reconcile and remove extras
share-pvc reconcile -f shares.yaml --prune
```

**Options:**
- `-f, --file FILE` - Manifest file (required)
- `--prune` - Delete shares not in manifest
- `--dry-run` - Show what would change
- `-v, --verbose` - Detailed output

## Manifest Format

### Basic Structure

```yaml
apiVersion: v1
kind: DFSShareConfig
metadata:
  name: my-shares-config
source:
  pvc: source-pvc-name
  namespace: source-namespace
targets:
  - pvc: target-pvc-name
    namespace: target-namespace
    readOnly: false
  - pvc: another-target
    namespace: another-namespace
    readOnly: true
labels:
  team: platform
  owner: ops-team
  project: shared-storage
```

### Complete Example

```yaml
apiVersion: v1
kind: DFSShareConfig
metadata:
  name: ml-dataset-shares
source:
  pvc: training-data
  namespace: ml-production
targets:
  - pvc: training-data
    namespace: ml-dev
    readOnly: false
  - pvc: training-data-ro
    namespace: ml-staging
    readOnly: true
  - pvc: validation-data
    namespace: ml-qa
    readOnly: true
labels:
  team: ml-engineering
  owner: ml-ops
  project: model-training
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `source.pvc` | Yes | Source PVC name |
| `source.namespace` | Yes | Source namespace |
| `targets[].pvc` | Yes | Target PVC name |
| `targets[].namespace` | Yes | Target namespace |
| `targets[].readOnly` | No | Read-only mount (default: false) |
| `labels` | No | Additional labels for tracking |

## Troubleshooting

### Source PVC Not Found
Ensure the source PVC exists and is bound:
```bash
kubectl get pvc <pvc-name> -n <namespace>
```

### Target Namespace Does Not Exist
Create the target namespace(s) before sharing:

```bash
kubectl create namespace <target-namespace>
```

### Permission Errors
Ensure you have sufficient RBAC permissions:

```bash
kubectl auth can-i create persistentvolumes
kubectl auth can-i create persistentvolumeclaims -n <target-namespace>
```

## Examples

See the [examples/](examples/) directory for additional manifest examples.

## Testing

The test suite validates all script functionality. See [tests/README.md](tests/README.md) for details.

## Support

For issues, questions, or contributions, please visit:
https://github.com/coreweave/reference-architecture/tree/main/storage/dfs-shared-pvc

