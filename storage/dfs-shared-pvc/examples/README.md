# DFS Shared PVC - Example Manifests

This directory contains example manifest files for sharing distributed file storage (DFS) PersistentVolumeClaims across Kubernetes namespaces using the VAST CSI driver.

## Quick Start

**1. Copy the customer example as a template:**
```bash
cp customer-example.yaml my-shares.yaml
```

**2. Edit the manifest with your PVC details:**
```bash
# Update the source PVC information
vim my-shares.yaml
```

**3. Validate your configuration:**
```bash
../share-pvc.sh validate -f my-shares.yaml
```

**4. Apply the shares:**
```bash
../share-pvc.sh apply -f my-shares.yaml
```

## Example Files

### customer-example.yaml
**Comprehensive template for customers**  
Contains detailed comments explaining each field, multiple example configurations, and best practices for labeling and organization.

**Use this file as your starting point!**

### manifest-example.yaml
Basic manifest showing ML dataset sharing across environments.

### multi-environment-share.yaml
Example of sharing configuration data to multiple environments (dev, qa, staging) with appropriate read-only settings.

### readonly-example.yaml
Demonstrates read-only sharing for analytics and reporting use cases.

### complete-example.yaml
Full-featured example with multiple source/target combinations and extensive labeling.

### sharedpvc-example.yaml
Original CRD-style example (for reference).

## Common Patterns

### Development Pipeline
Share production data to lower environments:
```yaml
source:
  pvc: prod-data
  namespace: production
targets:
  - pvc: dev-data
    namespace: development
    readOnly: false  # Devs can modify
  - pvc: staging-data
    namespace: staging
    readOnly: true   # Staging is read-only
```

### ML Data Pipeline
Share training data across ML teams:
```yaml
source:
  pvc: training-datasets
  namespace: ml-production
targets:
  - pvc: experiment-data
    namespace: data-science
    readOnly: false  # Scientists need to experiment
  - pvc: training-data
    namespace: ml-jobs
    readOnly: true   # Training jobs only read
```

### Cross-Team Collaboration
Share analytics data with different access levels:
```yaml
source:
  pvc: customer-analytics
  namespace: analytics-team
targets:
  - pvc: backend-data
    namespace: backend-services
    readOnly: false  # Backend needs write access
  - pvc: frontend-data
    namespace: frontend-services
    readOnly: true   # Frontend only reads
  - pvc: reporting-data
    namespace: business-intel
    readOnly: true   # BI reports only
```

## Manifest Operations

**List all shares:**
```bash
../share-pvc.sh list -f my-shares.yaml
```

**Validate before applying:**
```bash
../share-pvc.sh validate -f my-shares.yaml
```

**Apply/update shares:**
```bash
../share-pvc.sh apply -f my-shares.yaml
```

**Check for drift:**
```bash
../share-pvc.sh reconcile -f my-shares.yaml --dry-run
```

**Reconcile state:**
```bash
../share-pvc.sh reconcile -f my-shares.yaml
```

**Remove shares:**
```bash
../share-pvc.sh delete -f my-shares.yaml
```

## Best Practices

1. **Use Labels**: Add meaningful labels to track ownership, purpose, and lifecycle
   ```yaml
   labels:
     owner: team-name@company.com
     project: my-project
     environment: production
     created-date: "2026-01-08"
   ```

2. **Read-Only by Default**: Use `readOnly: true` unless write access is required
   - Prevents accidental data modifications
   - Safer for shared analytics/reporting use cases

3. **Clear Naming**: Use descriptive PVC names that indicate purpose
   ```yaml
   - pvc: ml-training-data-readonly  # Clear that it's read-only
     namespace: ml-training
     readOnly: true
   ```

4. **Version Control**: Store manifests in Git for tracking and rollback
   ```bash
   git add my-shares.yaml
   git commit -m "Add data sharing for ML pipeline"
   ```

5. **Validate First**: Always validate before applying
   ```bash
   ../share-pvc.sh validate -f my-shares.yaml && \
   ../share-pvc.sh apply -f my-shares.yaml
   ```

## Troubleshooting

**"Source PVC not found"**
- Ensure the source PVC exists: `kubectl get pvc -n <source-namespace>`
- Check the PVC name is spelled correctly

**"Source PV is not a VAST CSI volume"**
- Only VAST CSI PVCs can be shared
- Check: `kubectl get pv <pv-name> -o yaml | grep csi.vastdata.com`

**"Target namespace does not exist"**
- Create the namespace first: `kubectl create namespace <target-ns>`
- Or create it in your manifest

**Shares not appearing**
- List shares: `../share-pvc.sh list --source <namespace>/<pvc>`
- Check PV status: `kubectl get pv | grep shared-`

## Support

For more examples and detailed documentation, see:
- [../EXAMPLES.md](../EXAMPLES.md) - Comprehensive usage examples
- [../README.md](../README.md) - Full script documentation
- [CoreWeave Storage Documentation](https://docs.coreweave.com/storage)
