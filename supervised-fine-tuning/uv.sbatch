#!/usr/bin/env bash

#SBATCH --job-name=uv
#SBATCH --partition=b200
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=0
#SBATCH --time=1:00:00
#SBATCH --output=/mnt/data/fc-demo/logs/%x-%j.out

set -euo pipefail
ENV_DIR=/mnt/data/fc-demo
OUTPUT_DIR="$ENV_DIR/logs/"
mkdir -p "$OUTPUT_DIR"
cd "$ENV_DIR"

export UV_LINK_MODE=copy
export UV_CACHE_DIR=/mnt/data/fc-demo/.uv-cache
uv sync
