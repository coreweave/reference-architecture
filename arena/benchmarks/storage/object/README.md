# Object Storage Benchmarks

Benchmarks for CoreWeave AI Object Storage (CAIOS) and LOTA performance testing.

## Prerequisites

### 1. Environment File

Create `/mnt/data/env/.env` with your credentials:

```bash
# AWS/S3 Credentials
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=US-EAST-04A

# Endpoints
S3_ENDPOINT_URL=https://cwobject.com
LOTA_ENDPOINT_URL=http://cwlota.com

# Bucket name (REQUIRED) - use your org ID as prefix
S3_BUCKET=<orgid>-ailabs-benchmark
# Example: S3_BUCKET=poc049-ailabs-benchmark
```

### 2. Create Dummy Shards

Before running benchmarks, create test data in your bucket:

```bash
cd /mnt/data/ailabs/benchmarks/storage/object

# Make script executable
chmod +x create_dummy_shards.sh

# Create 128 x 2GB dummy shards (default)
./create_dummy_shards.sh

# Or specify number of shards
./create_dummy_shards.sh 128
```

This creates `shard_000000.dummy` through `shard_000127.dummy` (2GB each) in your S3 bucket.

## Running Benchmarks

### CPU-Pinned Test (Default)

Tests download bandwidth with 128 CPU workers:

```bash
sbatch submit_caios_lota_node_throughput_benchmark.slurm
```

### GPU-Pinned Test

Tests download bandwidth with workers pinned to GPUs:

```bash
sbatch submit_caios_lota_node_throughput_benchmark.slurm --gpu
```

### Monitor Job

```bash
# Check job status
squeue -u $USER

# View output (replace JOBID)
tail -f ailabs_benchmark_throughput__JOBID.out
```

## Files

| File | Description |
|------|-------------|
| `create_dummy_shards.sh` | Creates test data in S3 bucket |
| `caios_lota_node_throughput_benchmark.py` | Main benchmark script |
| `submit_caios_lota_node_throughput_benchmark.slurm` | Slurm job submission script |

## What the Benchmark Tests

- **CAIOS** (cwobject.com): Direct S3-compatible object storage
- **LOTA** (cwlota.com): Large Object Transfer Acceleration

Tests multiple configurations:
- Single-threaded downloads
- Multi-part downloads (512MB, 1024MB, 2048MB chunks)
- CPU-pinned vs GPU-pinned workers

## Output

Results show aggregate throughput in GB/s for each configuration, helping identify optimal settings for your workload.
