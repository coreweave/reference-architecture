#!/bin/bash
# Create dummy shard files for CAIOS/LOTA benchmark testing
#
# Usage: ./create_dummy_shards.sh [NUM_SHARDS]
#   NUM_SHARDS: Number of shards to create (default: 128)

set -e

# Load environment
if [ -f /mnt/data/env/.env ]; then
    source /mnt/data/env/.env
    export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION S3_ENDPOINT_URL S3_BUCKET
else
    echo "ERROR: Environment file not found at /mnt/data/env/.env"
    exit 1
fi

# Configuration
NUM_SHARDS=${1:-128}
SHARD_SIZE_GB=2
if [ -z "$S3_BUCKET" ]; then
    echo "ERROR: S3_BUCKET not set. Please set S3_BUCKET=<orgid>-arena-benchmark in /mnt/data/env/.env"
    exit 1
fi
BUCKET="$S3_BUCKET"
ENDPOINT=${S3_ENDPOINT_URL:-"https://cwobject.com"}
TMP_FILE="/tmp/shard_template.dummy"

echo "=========================================="
echo "CAIOS Dummy Shard Creator"
echo "=========================================="
echo "Bucket: $BUCKET"
echo "Endpoint: $ENDPOINT"
echo "Number of shards: $NUM_SHARDS"
echo "Shard size: ${SHARD_SIZE_GB}GB"
echo "=========================================="

# Create bucket if it doesn't exist
echo "Checking bucket..."
if aws s3api head-bucket --bucket "$BUCKET" --endpoint-url "$ENDPOINT" 2>/dev/null; then
    echo "Bucket '$BUCKET' exists"
else
    echo "Creating bucket '$BUCKET' in region '$AWS_DEFAULT_REGION'..."
    aws s3api create-bucket \
        --bucket "$BUCKET" \
        --endpoint-url "$ENDPOINT" \
        --create-bucket-configuration LocationConstraint="$AWS_DEFAULT_REGION"
    echo "Bucket created successfully"
fi

# Create template dummy file (2GB)
echo "Creating ${SHARD_SIZE_GB}GB template file..."
dd if=/dev/urandom of="$TMP_FILE" bs=1M count=$((SHARD_SIZE_GB * 1024)) status=progress

echo "Template file created: $(ls -lh $TMP_FILE | awk '{print $5}')"

# Upload first shard
echo ""
echo "Uploading shard_000000.dummy..."
aws s3 cp "$TMP_FILE" "s3://${BUCKET}/shard_000000.dummy" --endpoint-url "$ENDPOINT"

# Copy to remaining shards
echo ""
echo "Copying to remaining shards..."
for i in $(seq 1 $((NUM_SHARDS - 1))); do
    SHARD_NAME=$(printf "shard_%06d.dummy" $i)
    echo "  Copying to $SHARD_NAME..."
    aws s3 cp "s3://${BUCKET}/shard_000000.dummy" "s3://${BUCKET}/${SHARD_NAME}" --endpoint-url "$ENDPOINT"
done

# Cleanup
echo ""
echo "Cleaning up template file..."
rm -f "$TMP_FILE"

# Verify
echo ""
echo "=========================================="
echo "Verifying uploaded shards..."
echo "=========================================="
LISTING=$(aws s3 ls "s3://${BUCKET}/" --endpoint-url "$ENDPOINT" --human-readable)
echo "$LISTING" | head -10
echo "..."
echo "$LISTING" | tail -5
echo ""
echo "Total objects: $(echo "$LISTING" | wc -l)"

echo ""
echo "=========================================="
echo "Done! Created $NUM_SHARDS shards in s3://${BUCKET}/"
echo "=========================================="
