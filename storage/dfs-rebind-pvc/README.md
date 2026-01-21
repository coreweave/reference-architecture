# Rebind PVC

A Kubernetes utility script for rebinding Persistent Volume Claims (PVCs) across namespaces.

> **Note**: Always delete rebound (child) PVCs before deleting the original (base) PVC to avoid stale handles and stuck pods. See [CoreWeave PVMO Considerations](#coreweave-pvmo-considerations) for details.

## Overview

`rebind-pvc.sh` enables you to create new Kubernetes manifests that rebind an existing PVC's underlying storage volume to a different namespace. This preserves your data while allowing you to migrate workloads or share storage across namespaces.

## Prerequisites

- `kubectl` installed and configured with access to your cluster
- `jq` command-line JSON processor
- Appropriate RBAC permissions to read PVCs/PVs in the source namespace
- CSI-based storage volumes (the script is designed for CSI volumes)

## Installation & usage

Download the script: 

```bash
curl -O https://raw.githubusercontent.com/your-repo/rebind-pvc/main/rebind-pvc.sh
```

Make it executable: 

```bash
chmod +x rebind-pvc.sh
```
Example usage: 

```bash
./rebind-pvc.sh <original-pvc> <original-namespace> <new-namespace> [new-pvc-name]
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `original-pvc` | Yes | Name of the existing PVC |
| `original-namespace` | Yes | Namespace where the original PVC exists |
| `new-namespace` | Yes | Target namespace for the new PVC |
| `new-pvc-name` | No | Name for the new PVC (defaults to original PVC name) |

## Examples

### Basic Usage - Same PVC Name

Rebind a PVC named `data-volume` from namespace `old-app` to `new-app`:

```bash
./rebind-pvc.sh data-volume old-app new-app
```

This creates:
- `pvc-abc123-share-data-volume-new-app.yaml` - New PersistentVolume manifest (where `pvc-abc123` is the original PV name)
- `data-volume-new-app.yaml` - New PersistentVolumeClaim manifest

### Custom PVC Name

Rebind with a different name in the new namespace:

```bash
./rebind-pvc.sh data-volume old-app new-app renamed-data
```

This creates:
- `pvc-abc123-share-renamed-data-new-app.yaml` - New PersistentVolume manifest (where `pvc-abc123` is the original PV name)
- `renamed-data-new-app.yaml` - New PersistentVolumeClaim manifest

### Complete Workflow Example

```bash
# 1. Generate the manifests
./rebind-pvc.sh postgres-data production staging

# 2. Review the generated YAML files
cat pvc-xyz789-share-postgres-data-staging.yaml
cat postgres-data-staging.yaml

# 3. Apply the manifests
kubectl apply -f pvc-xyz789-share-postgres-data-staging.yaml
kubectl apply -f postgres-data-staging.yaml

# 4. Verify the new PVC is bound
kubectl get pvc postgres-data -n staging
kubectl get pv pvc-xyz789-share-postgres-data-staging
```

## How It Works

1. **Retrieves Original PVC Info**: Queries the source PVC to get the bound PersistentVolume name
2. **Extracts PV Metadata**: Collects all relevant information from the PV:
   - CSI volume handle (the actual storage identifier)
   - Storage class, capacity, and access modes
   - CSI driver information
   - Volume attributes and mount options
3. **Generates New PV Manifest**: Creates a new PersistentVolume pointing to the same underlying storage with:
   - Retain reclaim policy (to prevent data loss)
   - All original volume attributes preserved
4. **Generates New PVC Manifest**: Creates a PersistentVolumeClaim in the target namespace that binds to the new PV

The script generates declarative YAML manifests rather than directly modifying cluster resources, giving you full control over when and how to apply the changes.

## Naming Convention

The generated PersistentVolume uses the following naming pattern:

```
${ORIGINAL_PV}-share-${NEW_PVC}-${NEW_NS}
```

**Example**: If the original PV is `pvc-abc123`, the new PVC is `data-volume`, and the target namespace is `production`, the new PV will be named:
```
pvc-abc123-share-data-volume-production
```

## Important Notes

#### Proper teardown procedure

CoreWeave's [Persistent Volume Management Operator PVMO](https://docs.coreweave.com/docs/products/storage/distributed-file-storage/about-pvmo) will **delete the underlying storage** when the original (base) PVC is deleted, **regardless of whether rebound PVCs exist**. This can cause rebound PVCs to have stale volume handles and pods using rebound PVCs to become stuck during graceful shutdown.

When deleting resources created with this script on CoreWeave:

1. **Delete child PVCs first** (the rebound PVCs in target namespaces)
2. **Delete child PVs** (the rebound PersistentVolumes)
3. **Delete the base PVC last** (the original PVC in the source namespace)

#### Finding All Rebound Resources

To find all PVCs that may be sharing storage with a base PVC, you need to track which PVCs were created using this script. Consider:
- Documenting rebound relationships in your infrastructure-as-code
- Using naming conventions consistently
- Maintaining an inventory of rebindings

#### Namespace Requirements

- The target namespace must exist before applying the PVC manifest
- Ensure the storage class is available in the target namespace
- Verify RBAC permissions allow PVC creation in the target namespace

## Troubleshooting

### Pods Stuck During Teardown with Stale Volume Handles (CoreWeave)

**Symptom**: After deleting the base PVC, pods using rebound PVCs fail to terminate gracefully and show stale volume handle errors.

**Cause**: CoreWeave's PVMO deleted the underlying storage when the base PVC was deleted, leaving rebound PVCs pointing to non-existent storage.

**Solution**:
1. Force delete stuck pods:
   ```bash
   kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
   ```
2. Delete the rebound PVC:
   ```bash
   kubectl delete pvc <rebound-pvc-name> -n <namespace>
   ```
3. Delete the rebound PV:
   ```bash
   kubectl delete pv <rebound-pv-name>
   ```

**Prevention**: Always follow the proper deletion order - delete rebound PVCs first, then the base PVC. See [Proper teardown procedure](#proper-teardown-procedure).
