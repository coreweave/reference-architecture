# GCS to CAIOS Transfer

This solution provides a scalable, parallelized approach to migrate data from Google Cloud Storage to CoreWeave's object storage service. The solution uses Kubernetes jobs to run multiple concurrent rclone transfer tasks, enabling efficient transfer of large datasets.

## Features

- **Parallel Processing**: Splits file lists into shards for concurrent transfers
- **Scalable**: Configurable number of parallel workers and transfer parameters
- **Resumable**: Failed transfers can be retried with built-in backoff limits
- **Monitoring**: Built-in progress reporting and logging
- **Efficient**: Optimized rclone settings for high-throughput transfers

## Prerequisites

Before using this tool, ensure you have:

1. **CoreWeave Account**: Access to CoreWeave Cloud and CKS cluster
2. **Google Cloud Account**: Access to the source GCS buckets
3. **kubectl**: Installed and configured to access your CKS cluster
4. **gcloud CLI**: Installed and authenticated (for local testing)
5. **rclone**: Installed locally (for testing and shard uploads)

## Setup Instructions

### 1. Initial Setup

Clone this repository and navigate to the directory:
```bash
git clone https://github.com/coreweave/reference-architecture.git
cd reference-architecture/storage/gcs-caios-copy
```

### 2. Google Cloud Configuration

Set up your Google Cloud environment:
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set your project and preferred region/zone
gcloud config set project YOUR_PROJECT_ID
gcloud config set compute/region us-east1
gcloud config set compute/zone us-east1-c
```

### 3. Create Source and Destination Buckets

```bash
# Set your bucket names
export SHARDS_BUCKET="your-shards-bucket-name" 
export SOURCE_BUCKET="your-source-bucket-name"
export DESTINATION_BUCKET="your-destination-bucket-name"
```

If you're running this for a test/benchmark and don't have actual data to transfer, you can create a test bucket and upload some sample data:
```bash
# Create the source bucket in GCS
gcloud storage buckets create gs://$SOURCE_BUCKET --location=US-EAST1

# Upload your data to the source bucket
gcloud storage cp -r /path/to/your/data gs://$SOURCE_BUCKET
```

### 4. Service Account Setup

Create a Google Cloud service account with Storage Object Viewer permissions:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to IAM & Admin → Service Accounts
3. Create a new service account
4. Grant it the "Storage Object Viewer" role
5. Download the JSON key file and save it as `gcs-access-key.json`

### 5. CAIOS Credentials Setup
This step is optional and only needed if you are using s3cmd or a similar tool to query CAIOS directly. If you are using rclone, you can skip this step as rclone will handle the credentials through its configuration.

1. Obtain your CAIOS access keys from CoreWeave
2. Copy the template and fill in your credentials:
```bash
cp caios-keys.env.template caios-keys.env
```
3. Edit `caios-keys.env` with your actual CAIOS credentials

### 6. Configure rclone

#### Local Configuration (for testing)
```bash
cp local-rclone.conf.template local-rclone.conf
```
Edit `local-rclone.conf` and replace `KEY_ID_HERE` and `KEY_SECRET_HERE` with your CAIOS credentials. You can now use rclone this way:
```bash
rclone --config=local-rclone.conf ls caios:bucket
```

#### Kubernetes Configuration
```bash
cp rclone.conf.template rclone.conf
```
Edit `rclone.conf` and replace `KEY_ID_HERE` and `KEY_SECRET_HERE` with your CAIOS credentials.

### 7. Generate File Manifest

Create a manifest of all files to transfer and split into shards:

```bash
# Generate file list
gcloud storage ls -r "gs://$SOURCE_BUCKET/**" | sed "s/gs:\/\/$SOURCE_BUCKET\///g" > manifest.txt

# Split into 32 shards (adjust number as needed)
split -d -n l/32 manifest.txt shards/shard_
```

### 8. Upload Shards Config to CAIOS

```bash
# Install rclone locally if not already installed
sudo apt update && sudo apt install rclone -y

# Clear existing shards (if any)
rclone --config=local-rclone.conf purge caios:$SHARDS_BUCKET/shards

# Upload shard files to CAIOS
rclone --config=local-rclone.conf copy shards caios:$SHARDS_BUCKET/shards

# Verify upload
rclone --config=local-rclone.conf ls caios:$SHARDS_BUCKET
```

## Deployment to Kubernetes

### 1. Create Namespace and Secrets

```bash
# Create namespace
kubectl create namespace data-migration
kubectl config set-context --current --namespace=data-migration

# Create rclone configuration secret
kubectl create secret generic rclone-config \
  --from-file=rclone.conf=rclone.conf

# Create GCS service account secret
kubectl create secret generic gcs-service-account \
  --from-file=key.json=gcs-access-key.json
```

### 2. Configure the Job
Copy the job template and edit it:

```bash
cp job.yaml.template job.yaml
```

Edit `job.yaml` and update the following values:
- `SHARDS_BUCKET` environment variable: Use your shards inventory bucket name
- Update `<YOUR_GCS_BUCKET_NAME>` with your source GCS bucket name
- Update `<YOUR_CAIOS_BUCKET_NAME>` with your destination CAIOS bucket name

### 3. Deploy the Job

```bash
kubectl apply -f job.yaml
```

## Monitoring and Management

### Monitor Job Progress

```bash
# Check job status
kubectl get jobs

# Check pod status
kubectl get pods

# View logs from all pods
kubectl logs -l job-name=gcs-to-caios-copy -f

# View logs from a specific pod
kubectl logs gcs-to-caios-copy-<index> -f
```

### Adjust Performance Settings

The job includes several tunable parameters in `job.yaml`:

- **`completions`**: Number of shards (should match your shard count)
- **`parallelism`**: Number of concurrent pods
- **`cpu`/`memory`**: Resource allocation per pod

rclone transfer parameters can be adjusted in the job args:
- **`--transfers`**: Number of parallel file transfers
- **`--checkers`**: Number of parallel checksum operations
- **`--s3-chunk-size`**: Upload chunk size
- **`--s3-upload-concurrency`**: S3 upload concurrency

### Cleanup

```bash
# Delete the job
kubectl delete job gcs-to-caios-copy

# Delete secrets (optional)
kubectl delete secret rclone-config gcs-service-account

# Delete namespace (optional)
kubectl delete namespace data-migration
```

## Testing Locally

Before running the full Kubernetes job, test your configuration locally:

```bash
# Test a small transfer
time rclone copy gcs:$SOURCE_BUCKET/path/to/test/file caios:$DESTINATION_BUCKET \
     --config=local-rclone.conf \
     --transfers 64 --checkers 128 \
     --s3-upload-concurrency 12 --s3-chunk-size 100M \
     --multi-thread-streams 8 --multi-thread-cutoff 64M \
     --delete-excluded --progress --stats 3s
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Verify your service account key and CAIOS credentials
2. **Network Issues**: Check connectivity between CKS and both GCS and CAIOS
3. **Resource Limits**: Adjust CPU/memory requests if pods are being evicted
4. **Shard Format**: If using >99 shards, update the shard format in `job.yaml` to `shard_%03d`

## Configuration Reference

### Variables in job.yaml.template

| Variable | Description |
|----------|-------------|
| `SHARDS_BUCKET` | CAIOS bucket containing shard manifest files |
| `<YOUR_GCS_BUCKET_NAME>` | GCS source bucket name |
| `<YOUR_CAIOS_BUCKET_NAME>` | CAIOS destination bucket name |

### File Templates

| File | Purpose |
|------|---------|
| `caios-keys.env.template` | Template for CAIOS credentials |
| `local-rclone.conf.template` | rclone config for local testing |
| `rclone.conf.template` | rclone config for Kubernetes deployment |
| `job.yaml.template` | job manifest template for kubernetes deployment |

## Performance Optimization

- **Shard Count**: More shards = better parallelization, but more overhead
- **Pod Resources**: Increase CPU/memory for faster transfers per pod if bottlenecks occur
- **Transfer Settings**: Tune rclone parameters based on file sizes and network conditions
- **Parallelism**: Balance between throughput and resource usage
