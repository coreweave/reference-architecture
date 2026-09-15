#!/usr/bin/env bash

#SBATCH --job-name=qwen
#SBATCH --partition=b200
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=128
#SBATCH --mem=0
#SBATCH --exclusive
#SBATCH --time=2:00:00
#SBATCH --output=/mnt/data/fc-demo/fine_tuning/logs/%x-%j.out
#SBATCH --error=/mnt/data/fc-demo/fine_tuning/logs/%x-%j.out
#SBATCH --export=ALL

set -euo pipefail

export JOB=qwen/3.8-27b-pirate
export CONFIG=/mnt/data/fc-demo/fine_tuning/configs/${JOB}.yaml
export OUTPUT_DIR="/mnt/data/fc-demo/fine_tuning/outputs/${JOB}-${SLURM_JOB_ID}"
export MERGED_DIR=${OUTPUT_DIR}-merged
export ENV_DIR=/mnt/data/fc-demo
export WANDB_NAME=${JOB}-${SLURM_JOB_ID}

cd $ENV_DIR
mkdir -p "$OUTPUT_DIR"
source "$ENV_DIR/.venv/bin/activate"

GPUS_PER_NODE=8
head_node=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n1)
head_node_ip=$(getent hosts "$head_node" | awk '{print $1}')
head_node_port=29400

echo "Head node: $head_node ($head_node_ip:$head_node_port) | nodes=$SLURM_NNODES | gpus=$((SLURM_NNODES * GPUS_PER_NODE))"

export HF_HOME=/mnt/data/hf-cache
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTHONUNBUFFERED=1
export AXOLOTL_DO_NOT_TRACK=1

# triton cache will race if we put it on a shared filesystem
export TRITON_CACHE_DIR="/tmp/triton-cache"
rm -rf "$TRITON_CACHE_DIR"
mkdir -p "$TRITON_CACHE_DIR"

# stock ib / nccl env vars
export NCCL_DEBUG=WARN
export NCCL_SOCKET_IFNAME=eth0
export NCCL_IB_HCA=ibp
export UCX_TLS=tcp
export UCX_NET_DEVICES=eth0
export OMPI_MCA_coll_hcoll_enable=0
export PMIX_MCA_gds='^ds12'
export NCCL_NET_PLUGIN=none

export CUDA_DEVICE_ORDER=PCI_BUS_ID

export OMP_NUM_THREADS=16 # cpu threads / gpu

srun axolotl train "$CONFIG" \
  --output-dir "$OUTPUT_DIR" \
  --launcher torchrun -- \
  --nnodes "$SLURM_NNODES" \
  --nproc_per_node "$GPUS_PER_NODE" \
  --rdzv_id "$SLURM_JOB_ID" \
  --rdzv_backend c10d \
  --rdzv_endpoint "${head_node_ip}:${head_node_port}" \

echo "Rewriting adapter key names"
python fine_tuning/rewrite_adapter.py "$OUTPUT_DIR"

echo "Merging adapter into base model"
python fine_tuning/merge.py "$OUTPUT_DIR" "${MERGED_DIR}"


echo "Uploading merged model to CAIOS"
export CAIOS_ENDPOINT_URL="http://cwlota.com"
export CAIOS_BUCKET=${CAIOS_BUCKET:-myanello-fc}
export CAIOS_PREFIX=${CAIOS_PREFIX:-fine-tuned-models/${JOB}/${SLURM_JOB_ID}/}
python fine_tuning/upload.py --local-dir "${MERGED_DIR}" --endpoint "$CAIOS_ENDPOINT_URL" --bucket "$CAIOS_BUCKET" --prefix "$CAIOS_PREFIX"
