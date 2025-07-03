# CAIOS FUSE Mount

<div style="border-left: 4px solid #FFA500; padding: 10px; margin: 16px 0;">
    <span style="font-size: 20px; margin-right: 8px;">⚠️</span>
    <strong>Warning:</strong> Mounting CAIOS buckets via FUSE (object storage) significantly limits throughput and increases latency.  
    For optimal performance, use CAIOS through the S3 API directly.
</div>

This solution provides a way to mount a CAIOS (CoreWeave AI Object Storage) bucket as a filesystem using s3fs-fuse in your Kubernetes cluster. This allows applications to access CAIOS buckets as if they were local filesystems.

## Prerequisites

- Kubernetes cluster with CoreWeave CKS
- `kubectl` configured to access your cluster
- CAIOS bucket created and configured
- CAIOS access credentials (Access Key ID and Secret Access Key)

## Components

- **s3fs-fuse DaemonSet**: Runs on each node to mount CAIOS buckets as filesystems
- **Secret**: Stores CAIOS credentials securely
- **Test Pod**: Sample workload to verify the mount works correctly

## Installation

### 1. Prepare your environment variables

Set the required environment variables with your CAIOS credentials and configuration:

```bash
export CAIOS_ACCESS_KEY_ID=<YOUR_ACCESS_KEY_ID>           # replace with your CAIOS access key ID
export CAIOS_SECRET_ACCESS_KEY=<YOUR_SECRET_ACCESS_KEY>   # replace with your CAIOS secret access key
export CAIOS_BUCKET_NAME=<YOUR_BUCKET_NAME>               # replace with your CAIOS bucket name
export CAIOS_USER_GROUP_ID=<YOUR_USER_GROUP_ID>           # replace with your CAIOS user group ID
```
Your group ID depends on your desired file permissions. If you have no preference, you can remove the flag from the daemonset script or use 0 for root.

> **Note**: You can create CAIOS access keys following the [CoreWeave documentation](https://docs.coreweave.com/docs/products/storage/object-storage/how-to/manage-access-keys).

### 2. Deploy your kubernetes resources

```bash
# Create the namespace for the CAIOS S3FS daemonset
kubectl create namespace s3fs

# Create a CAIOS Access key and secret key for S3FS
printf '%s:%s\n' "$CAIOS_ACCESS_KEY_ID" "$CAIOS_SECRET_ACCESS_KEY" | kubectl -n s3fs create secret generic caios-passwd --from-file=passwd-s3fs=/dev/stdin
```

### 3. Deploy the s3fs DaemonSet

```bash
# Replace placeholders in the configuration files
sed -i "s|<YOUR_BUCKET_NAME>|$CAIOS_BUCKET_NAME|g" fuseds.yaml
sed -i "s|<YOUR_USER_GROUP_ID>|$CAIOS_USER_GROUP_ID|g" fuseds.yaml

# Deploy the s3fs DaemonSet
kubectl -n s3fs apply -f fuseds.yaml

# Deploy the test pod (optional)
kubectl -n s3fs apply -f testfuse.yaml
```

### 4. Verify the deployment

Check that the DaemonSet is running on all nodes:

```bash
kubectl -n s3fs get pods -l app=s3fs
```

Check that the test pod is running and check its logs (if you deployed it)

```bash
kubectl -n s3fs get deployment fusetest
kubectl logs -n s3fs deployment/fusetest --all-pods=true
```

### 5. Test the mount

You can test the CAIOS mount by accessing the test pod and verifying the filesystem:

```bash
# Access the test pod
kubectl -n s3fs exec -it deployment/fusetest -- /bin/bash

# List the contents of the mounted CAIOS bucket
ls -la /data/

# Create a test file
echo "Hello CAIOS FUSE!" > /data/test.txt

# Verify the file was created
cat /data/test.txt
```

## Performance Testing

The solution includes a sample FIO test to benchmark the CAIOS FUSE mount performance. You can run this test from within a pod that has the CAIOS mount:

```bash
kubectl -n s3fs exec -it deployment/fusetest -- fio \
    --name=cw-rand-read \
    --directory=/data/ \
    --rw=randread \
    --rwmixread=70 \
    --bs=64K \
    --numjobs=30 \
    --iodepth=12 \
    --size=1G \
    --filesize=1G \
    --time_based \
    --runtime=60 \
    --direct=1 \
    --ioengine=libaio \
    --fadvise_hint=0 \
    --group_reporting
```

## Usage in Your Applications

To use the CAIOS FUSE mount in your applications, add a `hostPath` volume to your pod specifications:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: your-app
spec:
  containers:
  - name: your-container
    image: your-image
    volumeMounts:
    - name: caios-data
      mountPath: /mnt/data
  volumes:
  - name: caios-data
    hostPath:
      path: /mnt/caios
      type: Directory
```

## Configuration

The main configuration files are:

- **`fuseds.yaml`**: DaemonSet configuration for s3fs-fuse
- **`testfuse.yaml`**: Test pod configuration

You can customize the mount options and configuration by modifying the `fuseds.yaml` file.

## Troubleshooting

### Check DaemonSet logs

```bash
kubectl -n s3fs logs -l app=s3fs-mounter
```

### Check test pod logs

```bash
kubectl -n s3fs logs deployment/fusetest --all-pods=true
```

### Verify secret creation

```bash
kubectl -n s3fs describe secret caios-passwd
```

### Check mount points on nodes

```bash
# SSH into a node and check mounts
mount | grep s3fs
```

## Cleaning up

To remove the CAIOS FUSE setup:

```bash
# Remove the test pod
kubectl -n s3fs delete -f testfuse.yaml

# Remove the DaemonSet
kubectl -n s3fs delete -f fuseds.yaml

# Remove the secret
kubectl -n s3fs delete secret caios-passwd

# Remove the namespace
kubectl delete namespace s3fs
```

## Important Notes

- The s3fs-fuse mount provides POSIX filesystem semantics over object storage, which may have different performance characteristics compared to native block storage
- Ensure your nodes have sufficient resources to run the s3fs-fuse processes
- The mount is available at `/mnt/caios` on each node
- Applications can access the CAIOS bucket through standard filesystem operations

## Security Considerations

- CAIOS credentials are stored as Kubernetes secrets
- CAIOS access keys will need to be permanent for the FUSE mount to work continuously
- The DaemonSet runs with elevated privileges to mount filesystems
- Ensure proper RBAC and network policies are in place for your environment
