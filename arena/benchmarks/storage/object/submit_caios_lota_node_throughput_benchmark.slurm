#!/bin/bash
#SBATCH --job-name=${JOB_NAME}
#SBATCH --partition=hpc-low
#SBATCH --nodes=1
#SBATCH --cpus-per-task=128
#SBATCH --gres=gpu:8
#SBATCH --time=01:00:00
#SBATCH --output=ailabs_benchmark_throughput_%j.out
#SBATCH --error=ailabs_benchmark_throughput_%j.err

set -e

# Load AWS credentials and endpoints from /mnt/data/env/.env
if [ -f /mnt/data/env/.env ]; then
    source /mnt/data/env/.env
    export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION S3_ENDPOINT_URL LOTA_ENDPOINT_URL S3_BUCKET
else
    echo "ERROR: Environment file not found. Please create /mnt/data/env/.env with:"
    echo "  AWS_ACCESS_KEY_ID=..."
    echo "  AWS_SECRET_ACCESS_KEY=..."
    echo "  AWS_DEFAULT_REGION=..."
    echo "  S3_ENDPOINT_URL=..."
    echo "  LOTA_ENDPOINT_URL=..."
    exit 1
fi

# Check for GPU flag
USE_GPU=false
if [[ "$1" == "--gpu" ]]; then
    USE_GPU=true
fi

echo "=========================================="
if [ "$USE_GPU" = true ]; then
    echo "Submitting GPU-Pinned Bandwidth Test"
    echo "=========================================="
    echo "Test: Workers pinned to GPUs downloading simultaneously"
else
    echo "Submitting CPU-Pinned Bandwidth Test"
    echo "=========================================="
    echo "Test: 128 CPU workers downloading simultaneously"
fi

if [ "$USE_GPU" = true ]; then
    JOB_NAME="gpu_bw"
    PYTHON_ARGS="--gpu"
    TEST_TYPE="GPU-Pinned"
else
    JOB_NAME="cpu_bw"
    PYTHON_ARGS=""
    TEST_TYPE="CPU-Pinned"
fi

echo "=========================================="
echo "${TEST_TYPE} Bandwidth Test"
echo "=========================================="
echo "Job ID: \$SLURM_JOB_ID"
echo "CPUs: \$SLURM_CPUS_PER_TASK"
if [ "$USE_GPU" = true ]; then
    echo "GPUs: 8"
fi
echo "=========================================="

echo "Python: \$(which python)"
python -c "import os; print(f'CPU cores: {os.cpu_count()}')"
if [ "$USE_GPU" = true ]; then
    python -c "import torch; print(f'GPUs: {torch.cuda.device_count()}')"
fi
echo "=========================================="

export PYTHONUNBUFFERED=0

python caios_lota_node_throughput_benchmark.py ${PYTHON_ARGS}

echo "=========================================="
echo "Test completed at: $(date)"
echo "=========================================="
