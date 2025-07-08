# CAIOS to DFS Transfer

This solution provides a high-performance, parallel data transfer mechanism from CAIOS (CoreWeave AI Object Storage) to DFS (Distributed File Storage) using rclone and SLURM. The solution leverages multiple nodes and processes to efficiently transfer large datasets.

## Prerequisites

- Access to CoreWeave HPC cluster with SLURM
- CAIOS bucket with data to transfer
- CAIOS access credentials (Access Key ID and Secret Access Key)
- Access to DFS mount points (`/mnt/data`)
- Home directory access (`/mnt/home`)

## Components

- **rclone**: High-performance file transfer tool with S3 compatibility
- **SLURM**: Job scheduler for parallel execution across multiple nodes
- **Configuration Template**: Pre-configured rclone settings for CAIOS
- **Parallel Processing**: Sharded file lists for concurrent transfers

## How It Works

1. **File Discovery**: Lists all files in the CAIOS bucket
2. **Sharding**: Splits the file list into multiple shards for parallel processing
3. **Parallel Transfer**: Uses SLURM to distribute transfer tasks across multiple nodes
4. **Optimized Performance**: Leverages rclone's advanced transfer options for maximum throughput

## Installation and Setup

### 1. **Prepare your environment variables**

Set the required environment variables for your transfer:

```bash
# replace with your CAIOS bucket name and DFS destination path
export WORK_DIR="/mnt/home/$USER/data-transfer"
export BUCKET_NAME="your-bucket-name"
export DESTINATION_PATH="/mnt/data"
```

### 2. **Set up the working directory**

Create and prepare your working directory:

```bash
mkdir -p $WORK_DIR
cd $WORK_DIR

# Copy the configuration files to your working directory
cp /path/to/reference-architecture/storage/caios-to-dfs/* $WORK_DIR/
```

### 3. **Configure CAIOS credentials**

Edit the rclone configuration with your CAIOS credentials:

```bash
cp local-rclone.conf.template local-rclone.conf

# Edit the configuration file
nano local-rclone.conf
```

Replace the following placeholders in `local-rclone.conf`:
- `KEY_ID` → Your CAIOS Access Key ID
- `KEY_SECRET` → Your CAIOS Secret Access Key

> **Note**: Use `https://cwobject.com/` as the endpoint if running on CPU nodes instead of `http://cwlota.com`.

### 4. **Prepare the transfer scripts**

Update the copy script with your environment variables:

```bash
sed -i "s|<WORK_DIR>|$WORK_DIR|g" copy.sh
sed -i "s|<BUCKET_NAME>|$BUCKET_NAME|g" copy.sh
sed -i "s|<DESTINATION_PATH>|$DESTINATION_PATH|g" copy.sh
```

### 5. **Generate file list and shards**

Discover all files in your CAIOS bucket and create shards for parallel processing:

```bash
# List all files in the bucket
srun --container-image=bitnami/rclone:latest \
    --container-mounts=/mnt/home:/mnt/home \
    /opt/bitnami/rclone/bin/rclone \
    --config=$WORK_DIR/local-rclone.conf \
    lsf -R --files-only --fast-list \
    caios:$BUCKET_NAME > $WORK_DIR/files.txt

# Create shards for parallel processing (64 shards by default)
mkdir -p $WORK_DIR/shards
split -d -n l/64 $WORK_DIR/files.txt $WORK_DIR/shards/shard_
```

## Running the Transfer

### Submit the SLURM job

```bash
# Submit the transfer job
sbatch transfer.slurm
```

### Monitor the job

```bash
# Check job status
squeue -u $USER

# Monitor transfer progress
tail -f transfer_out.<job_id>

# Check detailed logs
less transfer_out.<job_id>
```

## Configuration

### SLURM Job Configuration

The [`transfer.slurm`](storage/caios-to-dfs/transfer.slurm) file is configured with:

- **8 nodes** with **8 tasks per node** (64 total parallel processes)
- **14 CPUs per task** since it's what each node provides (can be tuned)
- **Exclusive node access** to use the whole node for the transfer

You can adjust these parameters based on your needs:

```bash
#SBATCH --nodes=8              # Number of nodes
#SBATCH --ntasks-per-node=8    # Tasks per node
#SBATCH --cpus-per-task=14     # CPUs per task
```

### Rclone Transfer Options

The transfer is optimized with the following rclone settings:

- `--transfers=128`: Up to 128 concurrent file transfers
- `--checkers=256`: 256 parallel checksum verifications
- `--multi-thread-streams=12`: 12 streams per large file
- `--multi-thread-cutoff=64M`: Use multi-threading for files > 64MB
- `--buffer-size=32M`: 32MB buffer for better performance
- `--ignore-existing`: Skip files that already exist at destination

### Adjusting Performance

You can modify the transfer parameters in [`copy.sh`](storage/caios-to-dfs/copy.sh):

```bash
# For larger files
--transfers=64
--checkers=128
```

## Monitoring and Troubleshooting

### Check transfer progress

```bash
# View real-time progress (updated every 10 minutes)
tail -f transfer_out.<job_id>
```

### Verify transfer completion

```bash
# Compare file counts
echo "Source files:" $(wc -l < $WORK_DIR/files.txt)
echo "Transferred files:" $(find $DESTINATION_PATH -type f | wc -l)

# Check for any failed transfers
grep -i "error\|failed" transfer_out.<job_id>
```

### Resume interrupted transfers

The transfer uses `--ignore-existing`, so you can safely re-run the job to resume interrupted transfers:

```bash
sbatch transfer.slurm
```

## Performance Optimization

### Network Considerations

- Use `https://cwobject.com/` endpoint when running on CPU nodes because only GPU nodes run LOTA
- Adjust `chunk_size` in rclone config based on your network characteristics
- Consider `upload_concurrency` settings for optimal throughput

## Example Usage

### Basic transfer workflow

```bash
# Set up environment
export WORK_DIR="/mnt/home/$USER/my-transfer"
export BUCKET_NAME="my-dataset"
export DESTINATION_PATH="/mnt/data/my-dataset"

# Prepare workspace
mkdir -p $WORK_DIR && cd $WORK_DIR
cp /path/to/caios-to-dfs/* .

# Configure credentials
cp local-rclone.conf.template local-rclone.conf
# Edit local-rclone.conf with your credentials

# Prepare for transfer
sed -i "s|<WORK_DIR>|$WORK_DIR|g" copy.sh
sed -i "s|<BUCKET_NAME>|$BUCKET_NAME|g" copy.sh
sed -i "s|<DESTINATION_PATH>|$DESTINATION_PATH|g" copy.sh

# Generate file list and shards
srun --container-image=bitnami/rclone:latest \
    --container-mounts=/mnt/home:/mnt/home \
    /opt/bitnami/rclone/bin/rclone \
    --config=$WORK_DIR/local-rclone.conf \
    lsf -R --files-only --fast-list \
    caios:$BUCKET_NAME > $WORK_DIR/files.txt

mkdir -p $WORK_DIR/shards
split -d -n l/64 $WORK_DIR/files.txt $WORK_DIR/shards/shard_

# Start the transfer
sbatch transfer.slurm
```

## Important Notes

- **Bandwidth Usage**: This solution can consume significant network bandwidth. Monitor your usage and adjust concurrency if needed.
- **Storage Space**: Ensure sufficient space at the destination before starting large transfers.
- **Incremental Transfers**: The `--ignore-existing` flag allows for safe re-runs and incremental updates.

## Security Considerations

- Store CAIOS credentials securely and avoid committing them to version control
- Ensure proper file permissions on configuration files containing credentials
- Use appropriate SLURM account limits to prevent resource abuse
- Monitor transfer logs for any security-related issues

## Cleaning Up

After successful transfer, you can clean up temporary files:

```bash
# Remove working directory (be careful with this command)
rm -rf $WORK_DIR

# Or just remove temporary files
rm $WORK_DIR/files.txt
rm -rf $WORK_DIR/shards/
```
