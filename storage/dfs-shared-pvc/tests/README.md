# Test Suite

Comprehensive test suite for DFS Shared PVC script. Validates functionality across 28 test scenarios.

## Requirements

**Cluster Access:**
- Active Kubernetes cluster connection via kubectl
- VAST CSI driver installed (csi.vastdata.com)
- StorageClass "shared-vast" available

**Permissions:**
- Create/delete PersistentVolumes (cluster-scoped)
- Create/delete PersistentVolumeClaims in multiple namespaces
- Create/delete Namespaces
- List/get resources for validation

**Resources Created:**
- Test namespaces (auto-cleanup)
- Test PVCs and PVs (auto-cleanup)
- Temporary YAML manifests (auto-cleanup)

**Automatic Cleanup:**
- All test resources removed after execution
- Use --skip-cleanup to preserve for debugging
- Use --cleanup-only to remove orphaned resources

## Usage

```bash
# Run all tests
./test-share-pvc.sh

# Run with detailed output
./test-share-pvc.sh --verbose

# Stop on first failure
./test-share-pvc.sh --eager-stop

# Preview tests without running
./test-share-pvc.sh --dry-run

# Clean up orphaned test resources
./test-share-pvc.sh --cleanup-only
```

## Test Coverage

| Test Name | Category | Description |
|-----------|----------|-------------|
| Prerequisites | Setup | Validates kubectl, script accessibility, VAST StorageClass availability |
| Basic Sharing | Core | Creates source PVC, shares to single target, verifies resources |
| Multiple Targets | Core | Shares one source to multiple target namespaces simultaneously |
| Read-Only Mode | Core | Creates read-only target PVC, verifies PV readOnly flag |
| Mixed Modes | Core | Shares with both RW and RO targets from same source |
| Data Validation | Core | Writes to source, reads from target, verifies data consistency |
| Idempotency | Core | Runs apply twice, confirms no duplicate resources created |
| Cleanup | Core | Validates proper cleanup of all managed resources |
| YAML Basic | Manifest | Applies basic manifest file, verifies all targets created |
| YAML Multi | Manifest | Applies manifest with multiple targets, validates each |
| YAML List | Manifest | Tests list command output with multiple shares |
| YAML Validate | Manifest | Validates manifest syntax and configuration |
| YAML Reconcile | Manifest | Syncs actual state to match manifest desired state |
| YAML Delete | Manifest | Removes all shares from manifest, validates cleanup |
| RO Configuration | Security | Verifies read-only flag correctly set on PV |
| Conflict Detection | Validation | Detects and preserves existing PVCs with same name |
| Orphaned Resources | Cleanup | Identifies and handles orphaned PVs/PVCs |
| Empty Manifest | Validation | Rejects manifests with no targets |
| Duplicate Targets | Validation | Handles duplicate target definitions via idempotency |
| Parser Lenience | Validation | Validates lenient YAML parser behavior (bash-based) |
| Special Characters | Edge Case | Handles special characters in resource names |
| Drift Detection | Validation | Detects configuration drift and missing resources |
| Reconcile Prune | Advanced | Removes targets not in manifest during reconciliation |
| Delete Dry-Run | Safety | Previews deletions without executing them |
| Force Delete | Safety | Bypasses confirmation prompts for automation |
| Non-VAST Rejection | Validation | Rejects PVCs not using VAST CSI driver |
| Exit Codes | Reliability | Validates proper exit codes for success/failure |
| Verbose Output | Observability | Confirms detailed logging when verbose flag used |

## Example Output

```
=== DFS Shared PVC Script Test Suite v1.0.0 ===
[TEST][1/28] Testing Prerequisites...
    [PASS] All prerequisites met
[TEST][2/28] Testing Basic Sharing...
    [PASS] Basic sharing test passed
[TEST][3/28] Testing Multiple Targets...
    [PASS] Multiple targets test passed
[TEST][4/28] Testing Read-Only Mode...
    [PASS] Read-only mode test passed
...
[TEST][26/28] Testing Non-VAST PVC Rejection...
    [SKIP] Non-VAST PVC not bound (standard storage class unavailable) - skipping driver validation test
[TEST][27/28] Testing Exit Code Correctness...
    [PASS] Exit code correctness test passed
[TEST][28/28] Testing Verbose Output Completeness...
    [PASS] Verbose output test passed
    [INFO] Cleaning up test resources...
    [INFO] Cleanup initiated (namespaces will be deleted in background)


=== Test Summary ===
Total Tests:    28
Passed:         28
Failed:         0
Skipped:        0
Pass Rate:      100%

All tests passed!
```

## Troubleshooting

**Test Failures:**
- Ensure cluster has VAST CSI driver installed
- Verify StorageClass "shared-vast" exists
- Check RBAC permissions for test operations
- Review verbose output: ./test-share-pvc.sh --verbose

**Orphaned Resources:**
- Clean up manually: ./test-share-pvc.sh --cleanup-only
- Or delete namespaces: kubectl delete ns share-pvc-test-*

**Permission Errors:**
- Verify cluster-admin or equivalent permissions
- Check: kubectl auth can-i create pv
- Check: kubectl auth can-i create pvc -n default
